#!/usr/bin/env python
#
# A pgq consumer that generates varnish purge requests to expire things from
# the frontend caches.
#
# Reads the file varnish_pgq.ini, wihch is a normal pgq configuration file.
# Will look for any section starting with varnish_purger_<name>, and start one
# purger for each such section purging from the frontend <name>.
#
# Each purger will run in a process of it's own, because pgq doesn't support
# running differet consumers in different threads.
#
# Purging is done by sending a regular GET request to /varnish-purge-url, with
# the regular expression to purge in the http header X-Purge-URL.
#
# Retrying is handled automatically by pgq. In case a subprocess dies, it will
# be restarted regularly by the remaining watchdog process.
#
#

import httplib
import signal
import sys
import time
from ConfigParser import ConfigParser
from multiprocessing import Process

import pgq

class VarnishPurger(pgq.Consumer):
	"""
	pgq consumer that purges URLs from varnish as they appear in the queue.
	"""

	def __init__(self, frontend):
		self.frontend = frontend
		super(VarnishPurger, self).__init__('varnish_purger_%s' % frontend, 'db', ['varnish_pgq.ini'])

	def process_batch(self, db, batch_id, ev_list):
		"Called by pgq for each batch of events to run."

		for ev in ev_list:
			if ev.type == 'P':
				# 'P' events means purge. Currently it's the only event
				# type we support.
				print "Purging '%s' on %s" % (ev.data, self.frontend)
				try:
					if self.do_purge(ev.data):
						ev.tag_done()
				except Exception, e:
					print "Failed to purge '%s' on '%s': %s" % (ev.data, self.frontend, e)
			else:
				print "Unknown event type '%s'" % ev.type


	def do_purge(self, url):
		"""
		Send the actual purge request, by contacting the frontend this
		purger is running for and sending a GET request to the special URL
		with our regexp in a special header.
		"""
		headers = {'X-Purge-URL': url}
		conn = httplib.HTTPConnection('%s.postgresql.org' % self.frontend)
		conn.request("GET", "/varnish-purge-url", '', headers)
		resp = conn.getresponse()
		conn.close()
		if resp.status == 200:
			return True

		print "Varnish purge returned status %s (%s)" % (resp.status, resp.reason)
		return False


class PurgerProcess(object):
	"""
	Wrapper class that represents a subprocess that runs a varnish purger.
	"""
	def __init__(self, frontend):
		self.frontend = frontend
		self.start()

	def start(self):
		self.process = Process(target=self._run, name=frontend)
		self.process.start()

	def _run(self):
		# NOTE! This runs in the client! Must *NOT* be called from the
		# parent process!

		# Start by turning off signals so we don't try to restart ourselves
		# and others, entering into possible infinite recursion.
		signal.signal(signal.SIGTERM, signal.SIG_DFL)
		signal.signal(signal.SIGQUIT, signal.SIG_DFL)
		signal.signal(signal.SIGHUP, signal.SIG_DFL)

		# Start and run the consumer
		print "Initiating run of %s" % self.frontend
		self.purger = VarnishPurger(frontend)
		self.purger.start()

	def validate(self):
		"""
		Validate that the process is running. If it's no longer running,
		try starting a new one.
		"""
		if not self.process.is_alive():
			# Ugh!
			print "Process for '%s' died!" % self.frontend
			self.process.join()
			print "Attempting restart of '%s'!" % self.frontend
			self.start()

	def terminate(self):
		"""
		Terminate the process runing this purger.
		"""
		print "Terminating process for '%s'" % self.frontend
		self.process.terminate()
		self.process.join()


# We need to keep the list of purgers in a global variable, so we can kill
# them off from the signal handler.
global purgers
purgers = []

def sighandler(signal, frame):
	print "Received terminating signal, shutting down subprocesses"
	for p in purgers:
		p.terminate()
	sys.exit(0)


if __name__=="__main__":
	cp = ConfigParser()
	cp.read('varnish_pgq.ini')

	# Trap signals that shut us down, so we can kill off our subprocesses
	# before we die.
	signal.signal(signal.SIGTERM, sighandler)
	signal.signal(signal.SIGQUIT, sighandler)
	signal.signal(signal.SIGHUP, sighandler)

	# Start one process for each of the configured purgers
	for frontend in [section[15:] for section in cp.sections() if section[:15] == 'varnish_purger_']:
		purgers.append(PurgerProcess(frontend))

	# Loop forever, restarting any worker process that has potentially died
	while True:
		for p in purgers:
			p.validate()
		time.sleep(10)