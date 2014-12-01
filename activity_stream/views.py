import facebook
from dateutil import parser

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.shortcuts import render, get_object_or_404
from django.views.generic import View
from .models import Stream, StreamItem, StreamConnection
from .forms import StreamForm
from broker.models import Connection
from broker.utils import twitter_client


def localize_datetime(d):
    if d.tzinfo:
        return d
    else:
        return timezone.make_aware(d, timezone.get_current_timezone())


def expand_tweet_urls(tweet):
    text = tweet.text
    if tweet.entities['urls']:
        for entity in tweet.entities['urls']:
            url = entity['url']
            expanded = entity['expanded_url']
            text = text.replace(url, expanded)
    return text


def ingest_tweet(tweet, streamconnection):
    tweet_text = expand_tweet_urls(tweet)

    try:
        item = StreamItem.objects.get(stream=streamconnection.stream,
                                      connection=streamconnection.connection,
                                      source_id=tweet.id, date=tweet.created_at.replace(tzinfo=timezone.utc))
    except ObjectDoesNotExist:

        item = StreamItem(stream=streamconnection.stream,
                          connection=streamconnection.connection,
                          source_id=tweet.id, date=tweet.created_at.replace(tzinfo=timezone.utc))

        item.title = tweet.id
        item.linked_url = ''
        item.picture = ''
        item.type = 'status'
        item.permalink = u'https://twitter.com/{}/status/{}'.format(streamconnection.connection.username, tweet.id)
        item.date = tweet.created_at
        item.source_id = tweet.id
        item.raw_data = tweet

        if 'media' in tweet.entities:
            # only accept one image for now
            for object in tweet.entities['media']:
                if object['type'] == 'photo':
                    item.picture = object['media_url']
                    item.picture_id = object['id']
                    item.type = 'photo'
                    url = tweet_text[object['indices'][0]:(object['indices'][1] + 1)]
                    tweet_text = tweet_text.replace(url, '').strip()

        if tweet.user.protected:
            item.is_published = False

        item.body = tweet_text
        item.save()


def update_twitter(streamconnection):
    api = twitter_client(streamconnection.connection)
    tweets = api.user_timeline(exclude_replies=True, include_rts=False, count=40, include_entities=True)
    for tweet in tweets:
        ingest_tweet(tweet, streamconnection)
    streamconnection.save()


def update_facebook(streamconnection):
    graph = facebook.GraphAPI(streamconnection.connection.token)
    try:
        statuses = graph.get_connections('me', 'statuses')['data']
        for status in statuses:
            ingest_fb(status, streamconnection, 'status')
    except facebook.GraphAPIError:
        pass

    try:
        photos = graph.get_connections(str(streamconnection.connection.uid), 'photos')['data']
        for photo in photos:
            ingest_fb(photo, streamconnection, 'photo')
    except facebook.GraphAPIError:
        pass


def ingest_fb(post, streamconnection, post_type):

    try:
        item = StreamItem.objects.get(stream=streamconnection.stream,
                                      connection=streamconnection.connection,
                                      source_id=post['id'], date=post['updated_time'])
    except ObjectDoesNotExist:

        item = StreamItem(stream=streamconnection.stream,
                          connection=streamconnection.connection,
                          source_id=post['id'], date=post['updated_time'])

        item.type = post_type
        item.date = localize_datetime(parser.parse(post['updated_time']))
        item.source_id = post['id']
        item.raw_data = post

        if post_type == 'status':
            item.title = u'{} posted a status update.'.format(post['from']['name'])
            item.body = post['message'].encode('unicode_escape')
            item.permalink = u'https://facebook.com/{}/posts/{}'.format(streamconnection.connection.uid, post['id'])

        if post_type == 'photo':
            item.title = u'{} posted a photo.'.format(post['from']['name'])
            if 'name' in post:
                item.body = post['name'].encode('unicode_escape')
            item.permalink = post['link']
            item.picture = post['source']
            if 'images' in post:
                w = post['width']
                for image in post['images']:
                    if image['width'] > w:
                        item.picture = image['source']
                        w = image['width']
                    if image['width'] == 480:
                        item.picture_med = image['source']
                    if image['width'] == 320:
                        item.picture_sm = image['source']

        if 'place' in post:
            if 'street' in post['place']['location']:
                item.street = post['place']['location']['street']
            if 'city' in post['place']['location']:
                item.city = post['place']['location']['city']
            if 'state' in post['place']['location']:
                item.state = post['place']['location']['state']
            if 'zip' in post['place']['location']:
                item.zip = post['place']['location']['zip']
            if 'country' in post['place']['location']:
                item.country = post['place']['location']['country']
            if 'longitude' in post['place']['location']:
                item.longitude = post['place']['location']['longitude']
            if 'latitude' in post['place']['location']:
                item.latitude = post['place']['location']['latitude']
            if 'id' in post['place']:
                item.place_id = post['place']['id']
            if 'name' in post['place']:
                item.place_name = post['place']['name']

        # hide posts from other people
        if int(post['from']['id']) != int(streamconnection.connection.uid):
            item.is_published = False

        # check privacy
        graph = facebook.GraphAPI(streamconnection.connection.token)
        fql_str = 'SELECT value, description FROM privacy WHERE id = {}'.format(post['id'])
        fql_obj = graph.fql(fql_str)
        if fql_obj:
            privacy = fql_obj[0]['value']
            item.privacy = privacy
            if privacy != 'EVERYONE':
                item.is_published = False

        item.save()


class ActivityStream(View):

    def get(self, request):
        stream, created = Stream.objects.get_or_create(user=User.objects.get(id=request.user.id))

        if not stream.streamconnection_set.all():
            return HttpResponseRedirect(reverse('activity_stream_settings'))
        else:
            for streamconnection in stream.streamconnection_set.all():
                if streamconnection.connection.provider == 'twitter':
                    _tweets = StreamItem.objects.filter(stream__user=stream.user, is_published=True,
                                                        connection__provider='twitter')
                    if not _tweets:
                        update_twitter(streamconnection)

                    if streamconnection.needs_refresh():
                        update_twitter(streamconnection)

                elif streamconnection.connection.provider == 'facebook':
                    statuses = StreamItem.objects.filter(stream__user=stream.user, is_published=True,
                                                         connection__provider='facebook')
                    if not statuses:
                        update_facebook(streamconnection)
                    if streamconnection.needs_refresh():
                        update_facebook(streamconnection)

                else:
                    pass  # in case the broker adds clients before activity_stream

        posts = stream.streamitem_set.filter(is_published=True).order_by('-date')

        context = dict(stream=stream, request=request, posts=posts)
        return render(request, 'activity_stream/list.html', context)


class ActivityStreamSettings(View):

    success = False

    def post(self, request):
        stream = get_object_or_404(Stream, user=request.user)
        stream_connections = stream.streamconnection_set.all().order_by('-id')
        form = StreamForm(request.POST, instance=stream)
        if form.is_valid():
            form.save()

            # manage StreamConnection preferences
            form_connections = form.cleaned_data['streamconnections']
            for connection in stream_connections:
                if connection in form_connections:
                    if not connection.is_published:
                        connection.is_published = True
                        connection.save()
                else:
                    if connection.is_published is True:
                        connection.is_published = False
                        connection.save()

            return HttpResponseRedirect('.?success=true')
        else:
            context = dict(connections=stream_connections, stream=stream, form=form, success=self.success)
            return render(request, 'activity_stream/settings.html', context)

    def get(self, request):
        streamconnections = StreamConnection.objects.filter(stream__user=request.user).order_by('-id')
        connections = Connection.objects.filter(user=request.user).order_by('-id')
        stream = get_object_or_404(Stream, user=request.user)
        form = StreamForm(instance=stream)
        form.fields['streamconnections'].queryset = streamconnections
        form.fields['streamconnections'].initial = streamconnections.filter(is_published=True)

        if 'success' in request.GET:
            if request.GET['success'] == 'true':
                self.success = True
        context = dict(connections=connections, stream=stream, form=form, success=self.success, request=request)
        return render(request, 'activity_stream/settings.html', context)
