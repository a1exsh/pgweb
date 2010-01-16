from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponse, Http404
from django.template import TemplateDoesNotExist, loader, Context
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db import connection

from datetime import date

from pgweb.util.decorators import ssl_required
from pgweb.util.contexts import NavContext
from pgweb.util.helpers import simple_form

# models needed for the pieces on the frontpage
from news.models import NewsArticle
from events.models import Event
from quotes.models import Quote
from models import Version, ImportedRSSFeed, ImportedRSSItem

# models needed for the pieces on the community page
from survey.models import Survey

# models and forms needed for core objects
from models import Organisation
from forms import OrganisationForm

# Front page view
def home(request):
	news = NewsArticle.objects.filter(approved=True)[:5]
	events = Event.objects.select_related('country').filter(approved=True, training=False, enddate__gt=date.today).order_by('startdate')[:3]
	quote = Quote.objects.filter(approved=True).order_by('?')[0]
	versions = Version.objects.all()
	planet = ImportedRSSItem.objects.filter(feed__internalname="planet").order_by("-posttime")[:5]

	traininginfo = Event.objects.filter(approved=True, training=True).extra(where=("startdate <= (CURRENT_DATE + '6 Months'::interval) AND enddate >= CURRENT_DATE",)).aggregate(Count('id'), Count('country', distinct=True))
	# can't figure out how to make django do this
	curs = connection.cursor()
	curs.execute("SELECT * FROM (SELECT DISTINCT(org) FROM events_event WHERE startdate <= (CURRENT_DATE + '6 Months'::interval) AND enddate >= CURRENT_DATE AND approved AND training AND org IS NOT NULL AND NOT org='') x ORDER BY random() LIMIT 3")
	trainingcompanies = [r[0] for r in curs.fetchall()]

	return render_to_response('index.html', {
		'title': 'The world\'s most advanced open source database',
		'news': news,
		'events': events,
		'traininginfo': traininginfo,
		'trainingcompanies': trainingcompanies,
		'quote': quote,
		'versions': versions,
		'planet': planet,
	})

# Community main page (contains surveys and potentially more)
def community(request):
	s = Survey.objects.filter(current=True)
	try:
		s = s[0]
	except:
		s = None
	planet = ImportedRSSItem.objects.filter(feed__internalname="planet").order_by("-posttime")[:7]
	return render_to_response('core/community.html', {
		'survey': s,
		'planet': planet,
	}, NavContext(request, 'community'))

# Generic fallback view for static pages
def fallback(request, url):
	if url.find('..') > -1:
		raise Http404('Page not found.')

	try:
		t = loader.get_template('pages/%s.html' % url)
	except TemplateDoesNotExist, e:
		raise Http404('Page not found.')
		
	# Guestimate the nav section by looking at the URL and taking the first
	# piece of it.
	try:
		navsect = url.split('/',2)[0]
	except:
		navsect = ''
	return HttpResponse(t.render(NavContext(request, navsect)))

# Edit-forms for core objects
@ssl_required
@login_required
def organisationform(request, itemid):
	return simple_form(Organisation, itemid, request, OrganisationForm)
