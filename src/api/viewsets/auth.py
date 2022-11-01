from rest_framework.response import Response
from rest_framework import viewsets

from rest_framework.authtoken.models import Token
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from api.permissions import IsDeviceUser

from django.contrib.auth import get_user_model
from device.models import Permission
from django.conf import settings

User = get_user_model()
PERMISSIONS_ADMIN = settings.PERMISSIONS_ADMIN


class AuthViewSet(viewsets.ViewSet):
    """
        View set to handle authentication.
    """
    permission_classes = ()
    authentication_classes = ()

    def sign_in(self, request, format=None):

        data = request.data

        username = data.get('username')
        password = data.get('password')

        error = None
        user_token = None
        user_data = None
        try:
            token_user = Token.objects.get(user__username=username)
            if token_user.user.check_password(password):
                user_data = {
                    'user_id': token_user.user.id,
                    'name': token_user.user.get_full_name(),
                    'email': token_user.user.email,
                    'devices': token_user.user.device_list(),
                    'isAdmin': token_user.user.has_permission(PERMISSIONS_ADMIN),
                    'isSuperuser': token_user.user.is_superuser
                }
                user_token = token_user.key
                resp_status = status.HTTP_200_OK
            else:
                resp_status = status.HTTP_400_BAD_REQUEST
                error = "Invalid username or password"
        except Token.DoesNotExist:
            resp_status = status.HTTP_400_BAD_REQUEST
            error = "Invalid username or password"

        data = {
            "success": False if error else True,
            "error": error,
            "userData": user_data,
            "token": user_token
        }
        return Response(status=resp_status, data=data)

    def sign_up(self, request, format=None):

        data = request.data

        username = data.get('username')
        email = data.get('email')
        password = data.get('password1')
        password_confirmation = data.get('password2')
        error = None
        user_token = None
        user_data = None
        if username is None or password is None:
            error = "username or password not provided."
            resp_status = status.HTTP_400_BAD_REQUEST
        if password != password_confirmation:
            error = "Passwords do not match"
            resp_status = status.HTTP_422_UNPROCESSABLE_ENTITY
        elif User.objects.filter(username=username).exists():
            error = "User with this username already exists"
            resp_status = status.HTTP_422_UNPROCESSABLE_ENTITY

        if error is None:
            next_subnet_mask = User.get_next_subnet_mask()
            dev_user = User(
                username=username,
                email=email,
                description="User through website",
                subnet_mask=next_subnet_mask,
            )
            dev_user.save()
            dev_user.set_password(password_confirmation)
            dev_user.save()
            permission_user, created = Permission.objects.get_or_create(name='User')
            if created:
                permission_user.save()
            dev_user.permissions.add(permission_user)
            dev_user.save()
            user_data = {
                'name': dev_user.get_full_name(),
                'email': dev_user.email,
                'devices': dev_user.device_list(),
                'isAdmin': dev_user.has_permission(PERMISSIONS_ADMIN)
            }
            token = Token(user=dev_user)
            token.generate_key()
            token.save()
            user_token = token.key
            resp_status = status.HTTP_200_OK

        data = {
            "success": False if error else True,
            "error": error,
            "userData": user_data,
            "token": user_token
        }
        return Response(status=resp_status, data=data)


class VerifyAuthViewSet(viewsets.ViewSet):
    """
        View set to handle authentication.
    """
    permission_classes = (IsAuthenticated, IsDeviceUser)

    def verify_auth(self, request, format=None):

        user_data = {
            'name': request.user.get_full_name(),
            'email': request.user.email,
            'devices': request.user.device_list(),
            'isAdmin': request.user.has_permission(PERMISSIONS_ADMIN)
        }

        data = {
            "userData": user_data,
        }

        return Response(data=data)
