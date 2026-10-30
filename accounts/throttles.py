from rest_framework.throttling import AnonRateThrottle


# Rates live in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].
class RegisterThrottle(AnonRateThrottle):
    scope = 'register'


class CodeSendThrottle(AnonRateThrottle):
    scope = 'code_send'


class CodeCheckThrottle(AnonRateThrottle):
    scope = 'code_check'


class LoginThrottle(AnonRateThrottle):
    scope = 'login'
