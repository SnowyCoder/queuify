
from typing import Iterable, Union
from django.core.files import File
from django.contrib.auth.models import Group

from core.testdb import on_testdb
from queuify import settings
from .models import User

def init_test():
    pass


def create_user(image=None, **kwargs) -> User:
    if image is not None:
        image = settings.TEST_MEDIA_ROOT / image
        image = File(image.open('rb'), name=image.name)

    kwargs['image'] = image
    user = User.objects.create_user(**kwargs)
    return user

def add_friends(user: User, friends: Union[User, Iterable[User]]):
    if isinstance(friends, User):
        friends = [friends]

    for friend in friends:
        user.friends.add(friend)
        friend.friends.add(user)


@on_testdb(priority=100)
def reset_db():
    User.objects.all().delete()
    # UserFriends deleted automatically!
    moderators = Group.objects.get_or_create(name='moderators')[0]

    print("Creating users...")
    User.objects.create_superuser("admin", password="password")
    carol = create_user(
        username="carolshaw",
        pronouns="she/her",
        first_name="Carol",
        last_name="Shaw",
        description="Game designer since before you were born",
        password="idontknowastrongpasswordmaybe",
        image="carol_shaw.jpg",
    )
    linus = create_user(
        username="torvalds",
        pronouns="he/him",
        first_name="Linus",
        last_name="Torvalds",
        password="isecretlyusewindows",
        description="This project is running on linux, right?",
        image="linus_torvalds.jpg",
    )
    ed = create_user(
        username="edsheeran",
        pronouns="he/him",
        first_name="Ed",
        last_name="Sheeran",
        password="Cmaj9add4add6(b13)(b5)",
        description="Guitar singer (partially irish!)",
        image="ed_sheeran.jpg",
    )
    margaret = create_user(
        username="hamilton",
        pronouns="she/her",
        first_name="Margaret",
        last_name="Hamilton",
        password="hamilton123",
        description="The, the books, the're falling, aaah, I'm trapped!",
        image="margaret_hamilton.jpg",
    )
    masahiro = create_user(
        username="Sora_Sakurai",
        pronouns="he/him",
        first_name="Masahiro",
        last_name="Sakurai",
        password="nintendont",
        description="お前はもう死んでいる",
        image="masahiro_sakurai.png",
    )
    molly = create_user(
        username="molly0xFF",
        pronouns="she/her",
        first_name="Molly",
        last_name="White",
        password="wikipiki",
        description="Ice-cream maker by day, Wikipedia editor by night😎",
        image="molly_white.jpg",
    )

    add_friends(molly, [linus, ed, carol])
    add_friends(ed, [margaret, linus])
    add_friends(masahiro, [linus, carol])

    margaret.friend_requests.add(masahiro)
    carol.friend_requests.add(linus)
    molly.friend_requests.add(masahiro)

    moderators.user_set.add(molly, linus)
