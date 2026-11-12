"""Sharing an event sends an invite: it only shows in the other person's
calendar once they accept (#29)."""
from unittest import mock

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from friends.models import Friendship
from notifications.models import Notification
from push.models import PushSubscription
from .models import Event, Share

DINNER = {'title': 'Dinner', 'start': '2026-11-20T19:00:00Z', 'end': '2026-11-20T21:00:00Z'}


@override_settings(VAPID_PRIVATE_KEY='private', VAPID_SUBJECT='mailto:test@example.com')
@mock.patch('push.send.webpush')
class InviteTests(APITestCase):
    def setUp(self):
        self.anna = User.objects.create_user('anna', password='pass12345')
        self.ben = User.objects.create_user('ben', password='pass12345')
        self.cleo = User.objects.create_user('cleo', password='pass12345')
        for friend in [self.ben, self.cleo]:
            Friendship.objects.create(from_user=self.anna, to_user=friend, accepted=True)

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def share_dinner(self, *people):
        """Anna makes Dinner and shares it with `people` through the API."""
        self.as_user(self.anna)
        response = self.client.post('/api/events/', {**DINNER, 'shared_with': list(people)}, format='json')
        self.assertEqual(response.status_code, 201)
        return response.data['id']

    def status_of(self, event_id, user):
        return Share.objects.get(event_id=event_id, user=user).status

    def kinds_for(self, user):
        return list(Notification.objects.filter(user=user).order_by('created').values_list('kind', flat=True))

    def my_calendar(self, user):
        self.as_user(user)
        return [event['title'] for event in self.client.get('/api/events/').data]

    # ---------- Being invited ----------

    def test_sharing_sends_an_invite_with_a_push(self, webpush):
        PushSubscription.objects.create(user=self.ben, endpoint='https://web.push.apple.com/ben', p256dh='k', auth='a')
        event_id = self.share_dinner('ben')
        self.assertEqual(self.status_of(event_id, self.ben), Share.WAITING)
        invite = Notification.objects.get(user=self.ben)
        self.assertEqual(invite.kind, Notification.INVITED)
        self.assertEqual(invite.message, 'anna invited you to “Dinner”')
        self.assertEqual(invite.event_id, event_id)
        self.assertEqual(webpush.call_count, 1)
        self.assertIn('anna invited you', webpush.call_args.kwargs['data'])

    def test_an_invite_is_not_in_my_calendar_until_i_accept(self, webpush):
        self.share_dinner('ben')
        self.assertEqual(self.my_calendar(self.ben), [])
        self.assertEqual(self.my_calendar(self.anna), ['Dinner'])  # the owner always has it

    def test_i_can_look_at_an_invite_before_answering(self, webpush):
        event_id = self.share_dinner('ben')
        self.as_user(self.ben)
        response = self.client.get(f'/api/events/{event_id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['my_status'], 'waiting')

    def test_invites_lists_only_unanswered_ones_soonest_first(self, webpush):
        self.share_dinner('ben')
        self.client.post('/api/events/', {
            'title': 'Lunch', 'start': '2026-11-18T12:00:00Z', 'end': '2026-11-18T13:00:00Z', 'shared_with': ['ben'],
        }, format='json')
        answered = self.client.post('/api/events/', {
            'title': 'Gym', 'start': '2026-11-17T08:00:00Z', 'end': '2026-11-17T09:00:00Z', 'shared_with': ['ben'],
        }, format='json').data['id']
        self.as_user(self.ben)
        self.client.post(f'/api/events/{answered}/decline/')
        titles = [event['title'] for event in self.client.get('/api/events/invites/').data]
        self.assertEqual(titles, ['Lunch', 'Dinner'])

    def test_invites_are_only_mine(self, webpush):
        self.share_dinner('ben')
        self.as_user(self.cleo)
        self.assertEqual(self.client.get('/api/events/invites/').data, [])

    # ---------- Answering ----------

    def test_accepting_puts_it_in_my_calendar_and_tells_the_owner(self, webpush):
        event_id = self.share_dinner('ben')
        self.as_user(self.ben)
        response = self.client.post(f'/api/events/{event_id}/accept/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Dinner')
        self.assertEqual(response.data['my_status'], 'accepted')
        self.assertEqual(self.my_calendar(self.ben), ['Dinner'])
        self.assertIsNotNone(Share.objects.get(event_id=event_id, user=self.ben).answered)
        told = Notification.objects.get(user=self.anna)
        self.assertEqual(told.message, 'ben accepted “Dinner”')

    def test_declining_keeps_it_out_and_tells_the_owner(self, webpush):
        event_id = self.share_dinner('ben')
        self.as_user(self.ben)
        self.assertEqual(self.client.post(f'/api/events/{event_id}/decline/').status_code, 204)
        self.assertEqual(self.my_calendar(self.ben), [])
        self.assertEqual(self.client.get('/api/events/invites/').data, [])
        self.assertEqual(self.client.get(f'/api/events/{event_id}/').status_code, 404)
        self.assertEqual(Notification.objects.get(user=self.anna).message, 'ben declined “Dinner”')

    def test_answering_twice_is_refused(self, webpush):
        event_id = self.share_dinner('ben')
        self.as_user(self.ben)
        self.client.post(f'/api/events/{event_id}/accept/')
        response = self.client.post(f'/api/events/{event_id}/decline/')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], 'You already accepted this invite.')
        self.assertEqual(self.status_of(event_id, self.ben), Share.ACCEPTED)

    def test_only_invited_people_can_answer(self, webpush):
        event_id = self.share_dinner('ben')
        for user in [self.cleo, self.anna]:  # not invited, and the owner
            self.as_user(user)
            self.assertEqual(self.client.post(f'/api/events/{event_id}/accept/').status_code, 404)

    def test_leaving_is_for_accepted_events_only(self, webpush):
        event_id = self.share_dinner('ben')
        self.as_user(self.ben)
        response = self.client.post(f'/api/events/{event_id}/leave/')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.status_of(event_id, self.ben), Share.WAITING)

    # ---------- What the owner sees and does ----------

    def test_the_owner_sees_everyones_answer(self, webpush):
        event_id = self.share_dinner('ben', 'cleo')
        self.as_user(self.ben)
        self.client.post(f'/api/events/{event_id}/accept/')
        self.as_user(self.anna)
        shares = self.client.get(f'/api/events/{event_id}/').data['shares']
        self.assertEqual(
            sorted((s['username'], s['status']) for s in shares), [('ben', 'accepted'), ('cleo', 'waiting')],
        )

    def test_adding_someone_later_invites_only_them(self, webpush):
        event_id = self.share_dinner('ben')
        self.client.patch(f'/api/events/{event_id}/', {'shared_with': ['ben', 'cleo']}, format='json')
        self.assertEqual(self.kinds_for(self.ben), [Notification.INVITED])  # not invited twice
        self.assertEqual(self.kinds_for(self.cleo), [Notification.INVITED])

    def test_editing_details_sends_nothing(self, webpush):
        event_id = self.share_dinner('ben')
        self.client.patch(f'/api/events/{event_id}/', {'title': 'Dinner at 8'}, format='json')
        self.assertEqual(self.kinds_for(self.ben), [Notification.INVITED])

    def test_unsharing_before_they_answer_cancels_the_invite(self, webpush):
        event_id = self.share_dinner('ben', 'cleo')
        self.as_user(self.cleo)
        self.client.post(f'/api/events/{event_id}/accept/')
        self.as_user(self.anna)
        self.client.patch(f'/api/events/{event_id}/', {'shared_with': []}, format='json')
        self.assertEqual(self.kinds_for(self.ben), [Notification.INVITED, Notification.INVITE_CANCELLED])
        self.assertEqual(
            Notification.objects.get(user=self.ben, kind=Notification.INVITE_CANCELLED).message,
            'anna cancelled “Dinner”',
        )
        self.assertEqual(self.kinds_for(self.cleo), [Notification.INVITED])  # had accepted: not "cancelled"

    def test_reticking_someone_who_declined_invites_them_again(self, webpush):
        event_id = self.share_dinner('ben')
        self.as_user(self.ben)
        self.client.post(f'/api/events/{event_id}/decline/')
        self.as_user(self.anna)
        self.client.patch(f'/api/events/{event_id}/', {'shared_with': []}, format='json')
        self.client.patch(f'/api/events/{event_id}/', {'shared_with': ['ben']}, format='json')
        self.assertEqual(self.status_of(event_id, self.ben), Share.WAITING)
        self.assertEqual(self.kinds_for(self.ben), [Notification.INVITED, Notification.INVITED])

    def test_invite_again_after_a_decline(self, webpush):
        event_id = self.share_dinner('ben')
        self.as_user(self.ben)
        self.client.post(f'/api/events/{event_id}/decline/')
        self.as_user(self.anna)
        response = self.client.post(f'/api/events/{event_id}/invite-again/', {'username': 'ben'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['shares'], [{'username': 'ben', 'status': 'waiting'}])  # the answer is up to date
        self.assertEqual(self.status_of(event_id, self.ben), Share.WAITING)
        self.assertEqual(self.kinds_for(self.ben), [Notification.INVITED, Notification.INVITED])
        self.assertEqual(self.my_calendar(self.ben), [])  # still has to accept

    def test_invite_again_only_for_people_who_declined(self, webpush):
        event_id = self.share_dinner('ben')
        waiting = self.client.post(f'/api/events/{event_id}/invite-again/', {'username': 'ben'}, format='json')
        self.assertEqual(waiting.status_code, 400)
        not_shared = self.client.post(f'/api/events/{event_id}/invite-again/', {'username': 'cleo'}, format='json')
        self.assertEqual(not_shared.status_code, 400)

    def test_only_the_owner_can_invite_again(self, webpush):
        event_id = self.share_dinner('ben', 'cleo')
        self.as_user(self.ben)
        self.client.post(f'/api/events/{event_id}/accept/')
        response = self.client.post(f'/api/events/{event_id}/invite-again/', {'username': 'cleo'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_deleting_tells_each_person_the_right_thing(self, webpush):
        dan = User.objects.create_user('dan', password='pass12345')
        Friendship.objects.create(from_user=self.anna, to_user=dan, accepted=True)
        event_id = self.share_dinner('ben', 'cleo', 'dan')
        self.as_user(self.ben)
        self.client.post(f'/api/events/{event_id}/accept/')
        self.as_user(dan)
        self.client.post(f'/api/events/{event_id}/decline/')
        self.as_user(self.anna)
        self.client.delete(f'/api/events/{event_id}/')
        self.assertEqual(self.kinds_for(self.ben)[-1], Notification.EVENT_DELETED)  # had accepted
        self.assertEqual(self.kinds_for(self.cleo)[-1], Notification.INVITE_CANCELLED)  # hadn't answered
        self.assertEqual(self.kinds_for(dan), [Notification.INVITED])  # had declined: not told again

    # ---------- Invites in the notifications list ----------

    def test_notifications_show_the_invite_status(self, webpush):
        event_id = self.share_dinner('ben')

        def invite_status():
            self.as_user(self.ben)
            invite = self.client.get('/api/notifications/').data['notifications'][-1]
            return invite['event'], invite['invite_status']

        self.assertEqual(invite_status(), (event_id, 'waiting'))
        self.client.post(f'/api/events/{event_id}/accept/')
        self.assertEqual(invite_status(), (event_id, 'accepted'))
        self.as_user(self.anna)
        self.client.delete(f'/api/events/{event_id}/')
        self.assertEqual(invite_status(), (None, 'cancelled'))

    def test_other_notifications_have_no_invite_status(self, webpush):
        event_id = self.share_dinner('ben')
        self.as_user(self.ben)
        self.client.post(f'/api/events/{event_id}/accept/')
        self.as_user(self.anna)
        told = self.client.get('/api/notifications/').data['notifications'][0]
        self.assertEqual(told['kind'], 'invite_accepted')
        self.assertIsNone(told['invite_status'])

    # ---------- Old data ----------

    def test_unfriending_removes_invites_too(self, webpush):
        event_id = self.share_dinner('ben')
        friendship = Friendship.objects.get(from_user=self.anna, to_user=self.ben)
        self.client.delete(f'/api/friends/{friendship.id}/')
        self.assertFalse(Share.objects.filter(event_id=event_id).exists())
        self.assertEqual(Event.objects.get(id=event_id).title, 'Dinner')
