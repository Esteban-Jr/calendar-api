from rest_framework.throttling import UserRateThrottle


# Stops anyone guessing usernames by sending lots of requests. Only sending
# counts; looking at the list doesn't.
class FriendRequestThrottle(UserRateThrottle):
    scope = 'friend_request'

    def allow_request(self, request, view):
        if request.method != 'POST':
            return True
        return super().allow_request(request, view)
