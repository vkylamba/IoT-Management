from allauth.socialaccount.providers.facebook.views import FacebookOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter
from rest_auth.registration.views import SocialLoginView
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework import status

from device.models import Permission, Subnet

from django.conf import settings
import logging
logger = logging.getLogger('django')

PERMISSIONS_ADMIN = settings.PERMISSIONS_ADMIN


def get_user_data(response):
    error = None
    resp_status = status.HTTP_400_BAD_REQUEST
    user_data = dict()
    if response.status_code in [200, 201]:
        token = response.data.get('key')
        token_user = Token.objects.get(key=token)
        next_subnet_mask = Subnet.get_next()
        if not hasattr(token_user.user, 'dev_user'):
            dev_user = User(
                user=token_user.user,
                description="User through social channels",
                subnet_mask=next_subnet_mask,
            )
            dev_user.save()
            permission_user, created = Permission.objects.get_or_create(name='User')
            if created:
                permission_user.save()
            dev_user.permissions.add(permission_user)
            dev_user.save()
            devices_list = dev_user.device_list()
        else:
            devices_list = token_user.user.device_list()
        try:
            user_data = {
                'name': token_user.user.get_full_name(),
                'email': token_user.user.email,
                'devices': devices_list,
                'isAdmin': token_user.user.has_permission(PERMISSIONS_ADMIN) if hasattr(token_user.user, 'dev_user') else False
            }
            resp_status = status.HTTP_200_OK
        except Exception as e:
            logger.error(e)
            error = str(e)

        data = {
            "success": False if error else True,
            "error": error,
            "userData": user_data,
            "token": token
        }
    return Response(status=resp_status, data=data)


class FacebookLogin(SocialLoginView):
    adapter_class = FacebookOAuth2Adapter
    client_class = OAuth2Client
    callback_url = settings.SERVER_URL

    def post(self, request, *args, **kwargs):
        response = super(FacebookLogin, self).post(request, args, kwargs)
        return get_user_data(response)


class GithubLogin(SocialLoginView):
    adapter_class = GitHubOAuth2Adapter
    client_class = OAuth2Client
    callback_url = settings.SERVER_URL

    def post(self, request, *args, **kwargs):
        response = super(GithubLogin, self).post(request, args, kwargs)
        return get_user_data(response)

    def get(self, request, *args, **kwargs):

        response = super(GithubLogin, self).get(request, args, kwargs)
        return get_user_data(response)
