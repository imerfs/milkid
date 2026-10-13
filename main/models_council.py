"""Village council: voting box (polls) and meeting calendar. Rows are scoped by the village text of the author's profile."""
from django.contrib.auth.models import User
from django.db import models

__all__ = ['CouncilPoll', 'CouncilPollVote', 'CouncilMeeting']


class CouncilPoll(models.Model):
    STATUS_CHOICES = [('open', 'باز'), ('closed', 'بسته')]

    title = models.CharField(max_length=200, verbose_name='موضوع')
    description = models.TextField(blank=True, max_length=2000, verbose_name='توضیحات')
    village = models.CharField(max_length=200, blank=True, db_index=True, verbose_name='روستا')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open', verbose_name='وضعیت')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='council_polls', verbose_name='ایجادکننده')
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'رای‌گیری شورا'
        verbose_name_plural = 'رای‌گیری‌های شورا'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def tally(self):
        counts = {'approve': 0, 'reject': 0, 'abstain': 0}
        for row in self.votes.values('choice').annotate(n=models.Count('id')):
            counts[row['choice']] = row['n']
        counts['total'] = sum(counts.values())
        return counts


class CouncilPollVote(models.Model):
    CHOICES = [('approve', 'موافق'), ('reject', 'مخالف'), ('abstain', 'ممتنع')]

    poll = models.ForeignKey(CouncilPoll, on_delete=models.CASCADE, related_name='votes')
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='council_poll_votes')
    choice = models.CharField(max_length=10, choices=CHOICES)
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'رای'
        verbose_name_plural = 'آرا'
        constraints = [models.UniqueConstraint(fields=['poll', 'member'], name='one_vote_per_member_per_poll')]


class CouncilMeeting(models.Model):
    STATUS_CHOICES = [('scheduled', 'برنامه‌ریزی شده'), ('held', 'برگزار شده'), ('cancelled', 'لغو شده')]

    title = models.CharField(max_length=200, verbose_name='عنوان')
    starts_at = models.DateTimeField(db_index=True, verbose_name='زمان')
    location = models.CharField(max_length=200, blank=True, verbose_name='مکان')
    agenda = models.TextField(blank=True, max_length=3000, verbose_name='دستور جلسه')
    village = models.CharField(max_length=200, blank=True, db_index=True, verbose_name='روستا')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='scheduled', verbose_name='وضعیت')
    attendees = models.ManyToManyField(User, blank=True, related_name='council_meetings', verbose_name='حاضرین')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'جلسه شورا'
        verbose_name_plural = 'جلسات شورا'
        ordering = ['starts_at']

    def __str__(self):
        return self.title
