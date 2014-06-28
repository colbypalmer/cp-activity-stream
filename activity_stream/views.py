from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.generic import View
from models import Stream, StreamItem, StreamConnection
from forms import StreamForm
from broker.models import Connection
from broker.utils import twitter_client
from open_facebook import OpenFacebook


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
    item, created = StreamItem.objects.get_or_create(stream=streamconnection.stream,
                                                     connection=streamconnection.connection,
                                                     connection_system_id=tweet.id,
                                                     date=tweet.created_at.replace(tzinfo=timezone.utc))
    if created:
        item.title = tweet.id
        item.body = tweet_text
        item.linked_url = ''
        item.picture = ''
        item.type = 'tweet'
        item.permalink = u'https://twitter.com/{}/status/{}'.format(streamconnection.connection.username, tweet.id)
        item.raw_data = tweet
        if tweet.user.protected:
            item.is_published = False
        item.save()


def update_twitter(streamconnection):
    api = twitter_client(streamconnection.connection)
    tweets = api.user_timeline(exclude_replies=True, include_rts=False, count=30)
    for tweet in tweets:
        ingest_tweet(tweet, streamconnection)
    streamconnection.save()


def update_facebook(streamconnection):
    facebook = OpenFacebook(streamconnection.connection.token)
    statuses = facebook.get('me/feed')['data']
    for status in statuses:
        ingest_fb(status, streamconnection)


def ingest_fb(post, streamconnection):
    try:
        item, created = StreamItem.objects.get_or_create(stream=streamconnection.stream,
                                                         connection=streamconnection.connection,
                                                         connection_system_id=post['id'], date=post['created_time'])
        if created:
            if 'name' in post:  # eliminate shared stories to stick with explicit shares
                item.title = post['name']
                item.body = post['message']
                item.linked_url = post['link']
                item.picture = post['picture']
                item.type = post['type']
            else:
                item.is_published = False

            item.permalink = u'https://facebook.com/{}/posts/{}'.format(streamconnection.connection.username,
                                                                        post['id'].split('_')[1])
            item.raw_data = post
            item.save()

    except KeyError:
        pass


class ActivityStream(View):

    def get(self, request):
        stream, created = Stream.objects.get_or_create(user=User.objects.get(id=1))

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
                        facebook = OpenFacebook(streamconnection.connection.token)
                        statuses = facebook.get('me/feed')['data']
                        for status in statuses:
                            # eliminate shared stories to stick with explicit link shares (for now)
                            try:
                                if status['name']:
                                    ingest_fb(status, streamconnection)
                            except KeyError:
                                break

                    if streamconnection.needs_refresh():
                        update_facebook(streamconnection)

                else:
                    pass  # in case the broker adds clients before activity_stream

        posts = stream.streamitem_set.all().order_by('-date')

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
