from google.appengine.api.images import get_serving_url
from google.appengine.ext import blobstore


class Image(object):
    def __init__(self, blob):
        self.blob = blob

    @classmethod
    def get_by_key(cls, key):
        return cls(blobstore.BlobInfo(blobstore.BlobKey(key)))

    @classmethod
    def find_all(cls, limit=100):
        all = blobstore.BlobInfo.all().fetch(limit)
        return [cls(i) for i in all]

    def get_info(self):
        """Returns a dictionary with basic image properties."""
        return {
            "content_type": self.blob.content_type,
            "creation": self.blob.creation,
            "filename": self.blob.filename,
            "size": self.blob.size,
        }

    def get_key(self):
        return str(self.blob.key())

    def get_filename(self):
        return self.blob.filename

    def get_uploaded_on(self):
        return self.blob.creation

    def get_size(self):
        return self.blob.size

    def get_url(self, size=None, crop=False):
        """Returns a URL for accessing the image with specified parameters.
        Size limits width and height, crop=True makes it square."""
        url = get_serving_url(self.blob.key(), size, crop)
        if url.startswith('http://'):
            url = url[5:]
        return url

    def get_code(self, size=None, crop=False):
        """Returns the wiki code to embed this image."""
        code = "Image:" + str(self.blob.key())
        if size is not None:
            code += ";size=" + str(size)
        if crop:
            code += ";crop"
        return "[[" + code + "]]"
