from django.db import models
from pgweb.util.bases import PgModel

class Quote(models.Model, PgModel):
	approved = models.BooleanField(null=False, default=False)
	quote = models.TextField(null=False, blank=False)
	who = models.CharField(max_length=100, null=False, blank=False)
	org = models.CharField(max_length=100, null=False, blank=False)
	link = models.URLField(null=False, blank=False)
	
	send_notification = True
	
	def __unicode__(self):
		if len(self.quote) > 75:
			return "%s..." % self.quote[:75]
		else:
			return self.quote