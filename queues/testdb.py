
from datetime import datetime, time, timedelta
import random
from typing import Iterable, Optional, Tuple
from core.testdb import on_testdb
from queuify import settings
from users.models import User
from .models import JoinMode, QQueue, QueueOpenRange, QueueUser, QueueUserRole, UserQueueReport, Ticket, secs_to_time, time_to_secs
from django.core.files import File
from queuify import settings
from django.contrib.auth.models import Group, Permission

def init_test():
    # This is just needed so that IDEs and tools don't remove the "unused" import.
    pass


def create_queue(
    image: Optional[str]=None,
    openings: Optional[Iterable[Optional[Iterable[int]]]]=None,
    **kwargs
) -> QQueue:
    if image:
        image = settings.TEST_MEDIA_ROOT / image
        image = File(image.open('rb'), name=image.name)
        kwargs['image'] = image
    q = QQueue(**kwargs)
    q.save()

    # the type is a bit scary, but openings is just a list of opening ranges list[range]
    # every index is a day, and a day can be closed (None) or a range of times (from_hour, to_hour)
    # to be a bit more
    if openings is not None:
        for day, o in enumerate(openings):
            if o is None:
                continue
            QueueOpenRange(
                queue=q,
                day=day,
                from_time=time(o[0]),
                to_time=time(o[1]),
            ).save()
    return q

def populate_queue(
    queue: QQueue,
    interested: Iterable[User],
    visits_per_day: Tuple[float, float],
    serve_time_mins: Tuple[float, float]=(10, 2),
    previous_days: int=32,
    next_days: int=16,
    user_cancel: float=0.2,
    queue_cancel: float=0.1,
    reports: float=0.04,
) -> None:
    print(f"Populating {queue.name}")
    now = datetime.now().astimezone() # Get local timezone time
    for iday in range(-previous_days, next_days):
        # \033[K is ANSI "erase to end of line"
        print(f"\r{iday}/{next_days}\033[K", end="")
        day = (now + timedelta(days=iday)).date()

        if queue.get_open_range(day) is None:
            # Queue is closed today
            continue

        visits = max(0, round(random.normalvariate(*visits_per_day)))
        for _ivisit in range(visits):
            visitor = random.choice(interested)
            bookable = queue.get_bookable_times(day, datetime.combine(day, time.min, now.tzinfo))

            if isinstance(bookable, tuple):
                requested_time = secs_to_time(random.randint(
                    time_to_secs(bookable[0]),
                    time_to_secs(bookable[1]),
                ))
            else:
                if len(bookable) == 0:
                    break # No more space left for today
                requested_time = random.choice(bookable)[0]

            requested_time = datetime.combine(day, requested_time, now.tzinfo)
            book_time = requested_time - timedelta(seconds=min(60*60*24, abs(random.normalvariate(60*60, 60*30))))
            t = Ticket(
                queue=queue,
                user=visitor,
                requested_time=requested_time,
                creation_time=book_time,
            )
            t.save()

            ticket_state = random.random()
            if ticket_state < user_cancel + queue_cancel:
                by_whom = 'user' if ticket_state < user_cancel else 'queue'

                t.cancel(by_whom, "Sorry, i can't", now=book_time + timedelta(minutes=1))
            elif iday < 0:
                served_time = requested_time + timedelta(minutes=max(0, random.normalvariate(*serve_time_mins)))
                t.serve(now=served_time)
            if random.random() < reports:
                UserQueueReport(
                    queue=queue,
                    user=visitor,
                    creation_time=requested_time,
                    reason=random.choice(['The shop does not exist', 'DMCA Takedown', 'Hey, what is this button?']),
                ).save()
    print()


@on_testdb(priority=50)
def reset_db():
    QQueue.objects.all().delete()

    view_reports_perm = Permission.objects.get(codename="manage_reports")
    view_stats_perm = Permission.objects.get(codename="view_all_stats")
    moderators = Group.objects.get_or_create(name='moderators')[0]
    moderators.permissions.add(view_reports_perm)
    moderators.permissions.add(view_stats_perm)

    users = list(User.objects.exclude(username="admin"))
    ed = User.objects.get(first_name="Ed")
    linus = User.objects.get(first_name="Linus")
    molly = User.objects.get(first_name="Molly")
    carol = User.objects.get(first_name="Carol")

    print("Creating queues...")
    ed_queue = create_queue(
        name="Ed's Guitar lessons",
        description="Want to learn how to play?",
        is_privacy_hidden=False,
        join_mode=JoinMode.FRIENDS_ONLY,
        image='ed_guitar.jpg',
        fixed_ticket_time_minutes=60,
        openings=[(14, 18), (14, 18), (14, 18), (14, 18)],
    )
    ed_queue.users.add(ed)

    linus_queue = create_queue(
        name="Local Plumber",
        description="Is a pipe slow ehm leaking? Your ol' Linus can patch it",
        is_privacy_hidden=True,# I mean, you don't want others to know you need a plumber
        join_mode=JoinMode.URL_ONLY,
        image="linus_plumber.jpg",
        fixed_ticket_time_minutes=40,
        openings=[None, None, (9, 18), (9, 18), (9, 18), (9, 16)],
    )
    linus_queue.users.add(linus)

    molly_queue = create_queue(
        name="Ice Cream is going great!",
        description="Best ice-cream from around the web",
        is_privacy_hidden=False,
        join_mode=JoinMode.PUBLIC,
        image="molly_ice_cream.jpg",
        openings=[(14, 20), None, None, None, (14, 20), (14, 20), (14, 20)],
    )
    molly_queue.users.add(molly)
    QueueUser(# By default QueueUserRole is admin, so we need to add employees manually
        queue=molly_queue,
        user=carol,
        role=QueueUserRole.EMPLOYEE,
    ).save()

    random.seed("thisisarandomstringimgeneratingrandomlyrandomrandom")

    populate_queue(
        queue=ed_queue,
        interested=[molly, linus],
        visits_per_day=(3, 1),# mu, sigma
    )

    populate_queue(
        queue=linus_queue,
        interested=list(filter(lambda x: x != linus, users)),
        visits_per_day=(4, 3),
        serve_time_mins=(20, 5),
    )

    populate_queue(
        queue=molly_queue,
        interested=list(filter(lambda x: x not in [molly, carol], users)),
        visits_per_day=(10, 2),
        serve_time_mins=(4, 4),
    )
