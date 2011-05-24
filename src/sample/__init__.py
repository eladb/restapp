from google.appengine.ext import db
import restapp

class Book(db.Model):
    title = db.StringProperty()
    author = db.StringProperty()
    publish_year = db.IntegerProperty()
    last_update = db.DateTimeProperty(auto_now = True)
    
    @property
    def isbn(self):
        return self.key().name()

class BooksEndpoint(restapp.Endpoint):
    root_url = "/books"

    def get(self, ctx):
        isbn = ctx.resource_path
        book = Book.get_by_key_name(isbn)
        if not book: raise restapp.errors.NotFoundError("Book with ISBN %s not found" % isbn)
        dict = restapp.utils.to_dict(book, 'isbn')
        return dict, book
    
    def query(self, ctx):
        books = Book.all()
        return [ restapp.utils.to_dict(b, 'isbn') for b in books ]
    
    def post(self, ctx):
        isbn = ctx.require('isbn')
        title = ctx.require('title')
        author = ctx.argument('author')
        publish_year = ctx.argument('publish_year')
        book = Book.get_or_insert(isbn)
        book.title = title
        book.author = author
        if publish_year: book.publish_year = int(publish_year)
        book.put()
        return isbn

def main():
    restapp.run_wsgi_restapp(BooksEndpoint)
    
if __name__ == "__main__":
    main()
