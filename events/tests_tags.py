"""Tags on events (CO/BE15): each person labels their own events; friends
don't see the tags on events shared with them; GET /api/tags/ lists mine."""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from .models import Event, Share, Tag


class EventTagTests(APITestCase):
    def setUp(self):
        self.anna = User.objects.create_user('anna', password='pass12345')
        self.ben = User.objects.create_user('ben', password='pass12345')
        self.client.force_authenticate(user=self.anna)

    def create(self, **extra):
        data = {'title': 'Match', 'start': '2026-11-20T15:00:00Z', 'end': '2026-11-20T17:00:00Z', **extra}
        return self.client.post('/api/events/', data, format='json')

    def test_create_with_tags_returns_them_a_to_z(self):
        response = self.create(tags=['work', 'football'])
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['tags'], ['football', 'work'])

    def test_tags_are_tidied_and_not_repeated(self):
        response = self.create(tags=['  Work ', 'work', 'WORK', 'Football'])
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['tags'], ['football', 'work'])
        self.assertEqual(Tag.objects.filter(owner=self.anna).count(), 2)

    def test_patch_replaces_tags(self):
        event_id = self.create(tags=['work']).data['id']
        response = self.client.patch(f'/api/events/{event_id}/', {'tags': ['gym']}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['tags'], ['gym'])

    def test_patch_without_tags_keeps_them(self):
        event_id = self.create(tags=['work']).data['id']
        response = self.client.patch(f'/api/events/{event_id}/', {'title': 'Renamed'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['tags'], ['work'])

    def test_patch_with_empty_list_clears_tags(self):
        event_id = self.create(tags=['work']).data['id']
        response = self.client.patch(f'/api/events/{event_id}/', {'tags': []}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['tags'], [])

    def test_tag_longer_than_30_characters_gives_400(self):
        response = self.create(tags=['x' * 31])
        self.assertEqual(response.status_code, 400)
        self.assertIn('tags', response.data)

    def test_blank_tag_gives_400(self):
        response = self.create(tags=['   '])
        self.assertEqual(response.status_code, 400)
        self.assertIn('tags', response.data)

    def test_tag_with_a_comma_gives_400(self):
        # ?tags= splits on commas, so a tag like "rock,pop" could never be found.
        response = self.create(tags=['rock,pop'])
        self.assertEqual(response.status_code, 400)
        self.assertIn('tags', response.data)
        self.assertEqual(Tag.objects.count(), 0)

    def test_more_than_20_tags_gives_400(self):
        response = self.create(tags=[f'tag{n}' for n in range(21)])
        self.assertEqual(response.status_code, 400)
        self.assertIn('tags', response.data)

    def test_event_without_tags_returns_empty_list(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['tags'], [])

    def test_each_person_has_their_own_tags(self):
        self.create(tags=['work'])
        self.client.force_authenticate(user=self.ben)
        self.create(tags=['work'])
        self.assertEqual(Tag.objects.filter(name='work').count(), 2)

    def test_friend_sees_no_tags_on_a_shared_event(self):
        event = Event.objects.create(
            title='Match', start='2026-11-20T15:00:00Z', end='2026-11-20T17:00:00Z', owner=self.anna,
        )
        event.tags.add(Tag.objects.create(owner=self.anna, name='football'))
        Share.objects.create(event=event, user=self.ben, status=Share.ACCEPTED)
        self.client.force_authenticate(user=self.ben)
        response = self.client.get(f'/api/events/{event.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['tags'], [])


class TagListTests(APITestCase):
    def setUp(self):
        self.anna = User.objects.create_user('anna', password='pass12345')
        self.ben = User.objects.create_user('ben', password='pass12345')

    def event_with(self, owner, *names):
        event = Event.objects.create(
            title='Plan', start='2026-11-20T15:00:00Z', end='2026-11-20T17:00:00Z', owner=owner,
        )
        for name in names:
            event.tags.add(Tag.objects.get_or_create(owner=owner, name=name)[0])
        return event

    def test_needs_a_login(self):
        response = self.client.get('/api/tags/')
        self.assertEqual(response.status_code, 401)

    def test_lists_only_my_used_tags_a_to_z(self):
        self.event_with(self.anna, 'work', 'football')
        self.event_with(self.anna, 'work')
        self.event_with(self.ben, 'secret')
        Tag.objects.create(owner=self.anna, name='unused')
        self.client.force_authenticate(user=self.anna)
        response = self.client.get('/api/tags/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, ['football', 'work'])
