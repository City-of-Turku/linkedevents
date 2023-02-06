from helusers.adapter import DefaultSocialAccountAdapter
from helusers.user_utils import update_user
from helusers.utils import username_to_uuid

from helevents.models import User



class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """Update user based on token information."""
        user = sociallogin.user

        # If the user hasn't been saved yet, it will be updated
        # later on in the sign-up flow.
        if not user.pk:
            try:
                user = User.objects.get(uuid=username_to_uuid(user.username))
                sociallogin.connect(request, user)                  # We have to connect the user if we want to login from django || respa admin using tunnistamo
            except User.DoesNotExist:
                return
        data = sociallogin.account.extra_data
        oidc = sociallogin.account.provider == 'turku_oidc'
        update_user(user, data, oidc)

    def populate_user(self, request, sociallogin, data):
        user = sociallogin.user
        exclude_fields = ['is_staff', 'password', 'is_superuser', 'id']
        user_fields = [f.name for f in user._meta.fields if f not in exclude_fields]
        for field in user_fields:
            if field in data:
                setattr(user, field, data[field])
        return user

    def save_user(self, request, sociallogin, form=None):
        u = sociallogin.user
        u.set_unusable_password()
        sociallogin.save(request)

        data = sociallogin.account.extra_data
        oidc = sociallogin.account.provider == 'turku_oidc'
        update_user(u, data, oidc)

        return u