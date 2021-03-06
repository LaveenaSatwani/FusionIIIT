import datetime

from django.contrib.auth.models import User
from django.db.models import Q

from .models import LeaveMigration, LeaveRequest, LeavesCount


def get_user_choices(user):

    """

    # This Hacky way is to avoid an unrecognized error caused by following code:
    ------------------------
        try:
            user_type = user.extrainfo.user_type
            USER_CHOICES = [(usr.username, "{} {}".format(usr.first_name, usr.last_name))
                            for usr in User.objects.filter(
                            ~Q(username=user.username),
                            Q(extrainfo__user_type=user_type))]
        except Exception as e:
            USER_CHOICES = []
    -------------------------

    """
    error = False

    try:
        user_type = user.extrainfo.user_type
    except Exception as e:
        error = True
        USER_CHOICES = []

    if not error:
        USER_CHOICES = [(usr.username, "{} {}".format(usr.first_name, usr.last_name))
                        for usr in User.objects.filter(
                        ~Q(username=user.username),
                        Q(extrainfo__user_type=user_type))]

    return USER_CHOICES


def get_special_leave_count(start, end, leave_name):
    from applications.academic_information.models import Holiday
    special_holidays = Holiday.objects.filter(holiday_name=leave_name)
    count = 0.0
    while start <= end:
        if not special_holidays.filter(holiday_date=start).exists():
            return -1
        count += 1.0
        start = start + datetime.timedelta(days=1)
    return count


def get_leave_days(start, end, leave_type, start_half, end_half):
    count = 0.0
    leave_name = leave_type.name
    if leave_name.lower() in ['restricted', 'vacation']:
        count = get_special_leave_count(start, end, leave_name.lower())
    else:
        while start <= end:
            if not start.weekday() in [5, 6]:
                count += 1.0

            start = start + datetime.timedelta(days=1)

    if start_half and start.weekday() not in [5, 6]:
        count -= 0.5
    if end_half and end.weekday() not in [5, 6]:
        count -= 0.5

    return count


def get_leaves(leave):
    mapping = dict()

    for segment in leave.segments.all():
        count = get_leave_days(segment.start_date, segment.end_date, segment.leave_type,
                               segment.start_half, segment.end_half)
        if segment in mapping.keys():
            mapping[segment] += count
        else:
            mapping[segment] = count

    return mapping


def restore_leave_balance(leave):
    to_restore = get_leaves(leave)
    for key, value in to_restore.items():
        count = LeavesCount.objects.get(user=leave.applicant, leave_type=key.leave_type,
                                        year=key.start_date.year)
        count.remaining_leaves += value
        count.save()


def deduct_leave_balance(leave):
    to_deduct = get_leaves(leave)
    for key, value in to_deduct.items():
        count = LeavesCount.objects.get(user=leave.applicant, leave_type=key.leave_type,
                                        year=key.start_date.year)
        count.remaining_leaves -= value
        count.save()


def get_pending_leave_requests(user):
    users = list(x.user for x in user.current_designation.all())
    requests = LeaveRequest.objects.filter(Q(requested_from__in=users), Q(status='pending'))
    return requests


def get_processed_leave_requests(user):
    pass


def create_migrations(leave):
    migrations = []
    applicant = leave.applicant
    for rep_segment in leave.replace_segments.all():
        mig_transfer = LeaveMigration(
            type_migration='transfer',
            on_date=rep_segment.start_date,
            replacee=applicant,
            replacer=rep_segment.replacer,
            replacement_type=rep_segment.replacement_type
        )
        mig_revert = LeaveMigration(
            type_migration='revert',
            on_date=rep_segment.end_date + datetime.timedelta(days=1),
            replacee=applicant,
            replacer=rep_segment.replacer,
            replacement_type=rep_segment.replacement_type
        )

        migrations += [mig_transfer, mig_revert]

    LeaveMigration.objects.bulk_create(migrations)
