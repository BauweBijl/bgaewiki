GAE_DIR=~/src/.gae
PACKAGE=gaewiki-`date +'%Y%m%d'`.zip

all:
	@echo "Available targets:"
	@echo "  clean    -- delete stale and temporary files"
	@echo "  release  -- upload a fresh snapshot"
	@echo "  serve    -- run a local server"
	@echo "  test     -- run unit tests"
	@echo "  upload   -- deploy to AppEngine"

clean:
	find -iregex '.*\.\(pyc\|rej\|orig\|zip\)' -delete

console:
	PYTHONPATH=$(GAE_DIR):$(GAE_DIR)/lib/django_0_96 python

test: test-syntax
	PYTHONPATH=.:$(GAE_DIR):$(GAE_DIR)/lib/django_0_96 python gaewiki/tests.py

test-syntax:
	pep8 -r --ignore E501 gaewiki/*.py

upload: .hg/gaepass
	cat .hg/gaepass | appcfg.py -e "$(MAIL)" --passin update .

serve: .tmp/blobstore
	dev_appserver.py --require_indexes --enable_sendmail --use_sqlite --blobstore_path=.tmp/blobstore --datastore_path=.tmp/datastore --skip_sdk_update_check -d -a 127.0.0.1 .

release:
	zip -q -x "*.zip" "*.pyc" ".*" -r -X $(PACKAGE) .
	googlecode_upload.py -s "GAEWiki snapshot from `date +'%Y-%m-%d'`" -p gaewiki -l Featured $(PACKAGE)

.tmp/blobstore:
	mkdir -p .tmp/blobstore

.hg/gaepass:
	$(EDITOR) .hg/gaepass
