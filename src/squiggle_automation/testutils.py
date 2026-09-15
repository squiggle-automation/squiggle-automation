import string

from django.utils.crypto import get_random_string


def random_password():
    """
    A random password, used by the tests so that no credentials are hard-coded in them.

    The first part is letters only, so that a generated password can never consist of digits
    alone and always passes the password validators (see AUTH_PASSWORD_VALIDATORS) when it is
    submitted through one of the password forms.
    """
    return get_random_string(12, allowed_chars=string.ascii_letters) + get_random_string(8)
