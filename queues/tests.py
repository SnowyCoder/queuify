from datetime import time, datetime
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone

from queues.models import JoinMode, QQueue, QueueOpenRange, QueueUser, QueueUserRole, Ticket, TicketState
from users.models import User


class QueueTests(TestCase):
    def test_is_open_at(self):
        queue = QQueue(
            name = "test_queue1",
        )
        r1 = QueueOpenRange(
            queue = queue,
            day = 0,
            from_time = time(9, 0),
            to_time = time(18, 0),
        )
        self.assertTrue(r1.is_open_at(time(15, 0)))
        self.assertFalse(r1.is_open_at(time(18, 0)))
        self.assertTrue(r1.is_open_at(time(9, 1)))

        queue.save()
        r1.save()

        self.assertTrue(queue.is_open_at(datetime(2022, 5, 30, 15, 13)))
        self.assertFalse(queue.is_open_at(datetime(2022, 5, 31, 15, 13)))
        self.assertFalse(queue.is_open_at(datetime(2022, 5, 30, 18, 10)))

    def test_visibility(self):
        uadmin = User.objects.create_user(username='test_visibility_admin', password='12345')
        uemployee = User.objects.create_user(username='test_visibility_employee', password='12345')
        uinvited = User.objects.create_user(username='test_visibility_invited', password='12345')
        unormal = User.objects.create_user(username='test_visibility_normal', password='12345')

        queue1 = QQueue(
            name = "test_visibility1",
            join_mode = JoinMode.INVITE,
        )
        queue1.save()

        QueueUser(queue=queue1, user=uadmin, role=QueueUserRole.OWNER).save()
        QueueUser(queue=queue1, user=uemployee, role=QueueUserRole.EMPLOYEE).save()

        self.assertTrue(queue1.is_visible_by(uadmin))
        self.assertTrue(queue1.is_visible_by(uemployee))
        self.assertFalse(queue1.is_visible_by(uinvited))
        self.assertFalse(queue1.is_visible_by(unormal))

        QueueUser(queue=queue1, user=uinvited, role=QueueUserRole.INVITED).save()
        self.assertTrue(queue1.is_visible_by(uinvited))
        self.assertFalse(queue1.is_visible_by(unormal))

        queue1.join_mode = JoinMode.FRIENDS_ONLY
        queue1.save()
        self.assertFalse(queue1.is_visible_by(uinvited))
        uadmin.friends.add(uinvited)
        uinvited.friends.add(uadmin)
        self.assertTrue(queue1.is_visible_by(uinvited))


    def test_queue_fixed_time_booking(self):
        u = User.objects.create_user(username='test_queue_fixed_time_booking', password='12345')

        timezone.activate(u.tz)

        q = QQueue(
            name = "test_queue_fixed_time_booking1",
        )
        q.save()
        day = datetime(2022, 1, 3, tzinfo=q.tz).date()
        now = datetime(2022, 1, 1, tzinfo=q.tz)
        self.assertIsNone(q.get_bookable_times(day, now))

        QueueOpenRange(
            queue=q,
            day=day.weekday(),
            from_time=time(9, 0),
            to_time=time(10, 0),
        ).save()

        self.assertEqual(q.get_bookable_times(day, now), (time(9), time(10)))
        t1 = Ticket(
            queue=q,
            user=u,
            requested_time=datetime.combine(day, time(9, 0), q.tz)
        )
        t1.save()
        self.assertEqual(q.get_bookable_times(day, now), (time(9), time(10)))

        q.fixed_ticket_time_minutes = 15 # 15 minutes
        q.save()

        self.assertEqual(q.get_bookable_times(day, now), [
            (time(9, 15), time(9, 30)),
            (time(9, 30), time(9, 45)),
            (time(9, 45), time(10, 0))
        ])
        t1.cancel('user', "oh no, i have no more time!")
        self.assertEqual(q.get_bookable_times(day, now), [
            (time(9,  0), time(9, 15)),
            (time(9, 15), time(9, 30)),
            (time(9, 30), time(9, 45)),
            (time(9, 45), time(10, 0))
        ])
        Ticket(
            queue=q,
            user=u,
            requested_time=datetime.combine(day, time(9, 0), q.tz)
        ).save()

        # Check unaligned tickets ()
        with self.assertRaises(ValidationError):
            Ticket(
                queue=q,
                user=u,
                requested_time=datetime.combine(day, time(9, 40), q.tz)# 40 -> unaligned (should be 30 or 45)
            ).save()

        Ticket(
            queue=q,
            user=u,
            requested_time=datetime.combine(day, time(9, 30), q.tz)
        ).save()


        self.assertEqual(q.get_bookable_times(day, now), [
            (time(9, 15), time(9, 30)),
            (time(9, 45), time(10, 0))
        ])

        Ticket(
            queue=q,
            user=u,
            requested_time=datetime.combine(day, time(9, 45), q.tz)
        ).save()

        self.assertEqual(q.get_bookable_times(day, now), [
            (time(9, 15), time(9, 30)),
        ])

        with self.assertRaises(ValidationError):
            Ticket(
                queue=q,
                user=u,
                requested_time=datetime.combine(day, time(9, 45), q.tz)
            ).save()

        # Save ticket in an unaligned slot
        q.fixed_ticket_time_minutes = None
        q.save()
        Ticket(
            queue=q,
            user=u,
            requested_time=datetime.combine(day, time(9, 16), q.tz)
        ).save()
        q.fixed_ticket_time_minutes = 15
        q.save()

        # Check that all of the spaces are booked
        self.assertEqual(q.get_bookable_times(day, now), [])
        with self.assertRaises(ValidationError):
            Ticket(
                queue=q,
                user=u,
                requested_time=datetime.combine(day, time(9, 30), q.tz)
            ).save()
