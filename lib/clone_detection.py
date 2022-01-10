import sys
import traceback

from tor_db import *
from sklearn.feature_extraction.text import TfidfVectorizer
from datetime import *
from tor_elasticsearch import *

CLONE_THRESHOLD = 0.9

@db_session
def set_clone_group(url_a, url_b):
	domain_a = Domain.find_by_url(url_a)
	domain_b = Domain.find_by_url(url_b)
	if domain_a.new_clone_group and domain_b.new_clone_group and domain_a.new_clone_group == domain_b.new_clone_group:
		return None
	domain_a = Domain.get_for_update(id=domain_a.id)
	domain_b = Domain.get_for_update(id=domain_b.id)
	if domain_a.new_clone_group:
		domain_b.new_clone_group = domain_a.new_clone_group
	elif domain_b.clone_group:
		domain_a.new_clone_group = domain_b.new_clone_group
	else:
		cg = CloneGroup()
		domain_a.new_clone_group = cg
		domain_b.new_clone_group = cg
	commit()
	return None


@db_session
def has_clone_group(url):
	domain = Domain.find_by_url(url)
	if domain.new_clone_group:
		return True
	return False

@db_session
def set_null_clone_group():
	db.execute("UPDATE domain SET new_clone_group = NULL;")

@db_session
def update_clone_group():
	db.execute("UPDATE domain SET clone_group = new_clone_group;")

@db_session
def get_domain_ids():
	# rider added 2021-7-28 disable time filter
	# event_horizon = datetime.now() - timedelta(hours=48)
	# domains = select(d.id for d in Domain for p in d.pages if d.last_alive != NEVER and p.is_frontpage==True and d.last_alive > event_horizon)
	domains = select(d.id for d in Domain for p in d.pages if d.last_alive != NEVER and p.is_frontpage==True)
	return domains[:]

@db_session
def get_domain_body_and_url(domain_id):
	domain = Domain.get(id = domain_id)
	frontpage = select(p for p in Page if p.domain==domain and p.is_frontpage == True).first()
	commit()
	if not frontpage:
		return (None, None)
	try:
		body = frontpage.get_body()
	except Exception as ex:
		# traceback.print_exc()
		print("Error: Cannot get front page.", ex, flush=True)
		return (None, None)
	return (body, domain.index_url())




def get_html():
	domain_ids = get_domain_ids()
	frontpage_index = []
	domain_index = []
	print(f"Assembling frontpage html... {len(domain_ids)} domains", flush=True)
	n = len(domain_ids)
	i = 1
	for did in domain_ids:
		if (i % 10) == 0:
			print("%d / %d" % (i,n), flush=True)
		i += 1
		body, url = get_domain_body_and_url(did)
		if not body:
			continue
		frontpage_index.append(body)
		domain_index.append(url)
	return (domain_index, frontpage_index)


def detect():
	if not is_elasticsearch_enabled():
		raise NotImplementedError("Sorry, need elasticsearch support")

	domain_index, frontpage_index = get_html()
	print("Performing similarity matrix comparison...", flush=True)
	tfidf = TfidfVectorizer().fit_transform(frontpage_index)
	pairwise_similarity = tfidf * tfidf.T

	set_null_clone_group()
	matrix = pairwise_similarity.A
	print("Constructing clone groups...", flush=True)
	total = len(frontpage_index)
	for i in range(0, total):
		comparisons = matrix[i]
		url_a = domain_index[i]
		if ((i+1) % 10) == 0:
			print("processed %d / %d" % (i+1,total), flush=True)
		if has_clone_group(url_a):
			continue
		for j in range(i+1, len(frontpage_index)):
			score = comparisons[j]
			if score > CLONE_THRESHOLD:
				url_b = domain_index[j]
				print("Clone detected (score %f) #1 %s #2 %s" % (score, url_a, url_b), flush=True)
				set_clone_group(url_a, url_b)

	update_clone_group()
