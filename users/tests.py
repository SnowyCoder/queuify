from django.test import TestCase
from django.urls import reverse
from .models import User

class UsersCase(TestCase):
    def setUp(self):
        self.acredentials = {
            "username": "test_users_a",
            "password": "ablablabala",
        }
        self.auser = User.objects.create_user(
            first_name="Arnaldo",
            last_name="Aristogatto",
            pronouns="it/bit",
            description="Hello, I'm a test user, weeeee!",
            **self.acredentials,
        )

        self.bcredentials = {
            "username": "test_users_b",
            "password": "bblbblbbblb",
        }
        self.buser = User.objects.create_user(
            first_name="Bertozzi",
            last_name="Birimbumbim",
            pronouns="it/bit",
            description="What is this place?",
            **self.bcredentials,
        )

        self.ccredentials = {
            "username": "test_users_c",
            "password": "search",
        }
        self.cuser = User.objects.create_user(
            first_name="Coriandolo",
            last_name="Coroccoccocchi",
            pronouns="ity/bity",
            description="Can you C me?",
            **self.ccredentials,
        )
        # Situation:
        # a <-> b (a and b are friends)
        # a  -> c (a sent a request to c)
        self.auser.friends.add(self.buser)
        self.buser.friends.add(self.auser)
        self.auser.friend_requests.add(self.cuser)

    def test_search(self):
        self.client.login(**self.acredentials)

        # Search for a friend (contains search)
        res = self.client.get(reverse('users:search'), data={"q": 'users_b'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['result'], [self.buser])
        self.assertContains(res, 'Friend!')

        # Search for a non-friend
        res = self.client.get(reverse('users:search'), data={"q": 'c'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['result'], [self.cuser])
        self.assertNotContains(res, 'Friend!')

        # Search for you
        res = self.client.get(reverse('users:search'), data={"q": 's_a'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['result'], [self.auser])
        self.assertContains(res, 'You!')

    def test_make_request(self):
        self.client.login(**self.bcredentials)

        res = self.client.get(reverse('users:friends'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(list(res.context['friends']), [self.auser])
        self.assertEqual(list(res.context['friend_requests']), [])
        self.assertEqual(list(res.context['received_friend_requests']), [])

        # As User B request C's friendship
        res = self.client.post(reverse('users:add_friend', args=[self.cuser.id]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertTrue('Friend request sent' in list(res.context['messages'])[0].message)

        res = self.client.get(reverse('users:friends'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(list(res.context['friends']), [self.auser])
        self.assertEqual(list(res.context['friend_requests']), [self.cuser])
        self.assertEqual(list(res.context['received_friend_requests']), [])

    def test_accept_request(self):
        self.client.login(**self.ccredentials)

        res = self.client.get(reverse('users:friends'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(list(res.context['friends']), [])
        self.assertEqual(list(res.context['friend_requests']), [])
        self.assertEqual(list(res.context['received_friend_requests']), [self.auser])

        # add_user is both used to request friendship and to accept friendships.
        # As User C accept A's friendship request
        res = self.client.post(reverse('users:add_friend', args=[self.auser.id]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertTrue('Friendship accepted' in list(res.context['messages'])[0].message)

        res = self.client.get(reverse('users:friends'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(list(res.context['friends']), [self.auser])
        self.assertEqual(list(res.context['friend_requests']), [])
        self.assertEqual(list(res.context['received_friend_requests']), [])

    def test_re_request_frienship(self):
        self.client.login(**self.acredentials)

        res = self.client.get(reverse('users:friends'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(list(res.context['friends']), [self.buser])
        self.assertEqual(list(res.context['friend_requests']), [self.cuser])
        self.assertEqual(list(res.context['received_friend_requests']), [])

        # As user A try to re-request C's friendship, this will return an error message since
        # C's friendship has already been requested
        res = self.client.post(reverse('users:add_friend', args=[self.cuser.id]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertTrue('You cannot request' in list(res.context['messages'])[0].message)

        res = self.client.get(reverse('users:friends'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(list(res.context['friends']), [self.buser])
        self.assertEqual(list(res.context['friend_requests']), [self.cuser])
        self.assertEqual(list(res.context['received_friend_requests']), [])

    def test_request_frienship_to_friend(self):
        # This should not be possible without a custom POST request, but we should
        # still handle these cases
        self.client.login(**self.bcredentials)

        res = self.client.post(reverse('users:add_friend', args=[self.auser.id]), follow=True)
        self.assertTrue('You cannot request' in list(res.context['messages'])[0].message)

        res = self.client.get(reverse('users:friends'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(list(res.context['friends']), [self.auser])
        self.assertEqual(list(res.context['friend_requests']), [])
        self.assertEqual(list(res.context['received_friend_requests']), [])
