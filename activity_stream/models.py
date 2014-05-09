import datetime
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from broker.models import Connection


class Stream(models.Model):
    """
    The basic class of a User's connections, with a global `is_published` on/off switch.
    """
    user = models.ForeignKey(User)
    is_published = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now_add=True, auto_now=True, editable=False)

    def __unicode__(self):
        return u'{} {}'.format(self.user.username, self.pk)

    def save(self, *args, **kwargs):
        # make sure we have StreamConnections for each active connection
        connections = Connection.objects.filter(user=self.user, is_active=True)
        for connection in connections:
            sc, created = StreamConnection.objects.get_or_create(stream=self, connection=connection)
            if not created and not self.is_active:
                sc.is_active = self.is_active
                sc.save()
        super(Stream, self).save(*args, **kwargs)



class StreamConnection(models.Model):
    """
    A wrapper class to hold individual connection preferences, per stream.
    """
    stream = models.ForeignKey(Stream)
    connection = models.ForeignKey(Connection)
    stream_refresh_hours = models.IntegerField(default=1)  # 2
    post_delay_hours = models.IntegerField(default=0)  # 1
    is_published = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now_add=True, auto_now=True, editable=False)

    def __unicode__(self):
        return u'Stream {}: {} ({})'.format(self.stream.id, self.connection.username, self.connection.provider.title())

    def needs_refresh(self):
        now_adjusted = datetime.datetime.utcnow().replace(tzinfo=timezone.utc) + datetime.timedelta(hours=int(self.post_delay_hours))
        refresh_window = self.updated + datetime.timedelta(hours=int(self.stream_refresh_hours))
        return now_adjusted > refresh_window


class StreamItem(models.Model):
    """
    The individual posts in the Stream.
    """
    stream = models.ForeignKey(Stream)
    connection = models.ForeignKey(Connection)
    type = models.CharField(max_length=50)
    date = models.DateTimeField()
    title = models.CharField(max_length=255)
    body = models.TextField()
    picture = models.URLField(null=True, blank=True, max_length=300)
    linked_url = models.URLField(null=True, blank=True, max_length=255)
    connection_system_id = models.CharField(max_length=255)
    permalink = models.URLField()
    is_published = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now_add=True, auto_now=True, editable=False)

    def __unicode__(self):
        return u''.format(self.title)


@receiver(post_save, sender=Connection)
def sync_streamconnection(sender, **kwargs):
    instance = kwargs['instance']
    streams = Stream.objects.filter(user=instance.user, is_active=True)
    for stream in streams:
        sc, created = StreamConnection.objects.get_or_create(stream=stream, connection=instance)
        sc.is_active = instance.is_active
        sc.save()
