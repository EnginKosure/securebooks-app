"""
SecureBooks FastAPI Application
A minimal book catalog app with PostgreSQL backend.
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import psycopg2
from pydantic import BaseModel
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SecureBooks", version="1.0.0")

# CORS middleware for demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration from environment variables
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "securebooks")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    logger.error(f"Failed to create database engine: {e}")
    SessionLocal = None

Base = declarative_base()


class BookModel(Base):
    """SQLAlchemy Book model"""
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), index=True, nullable=False)
    author = Column(String(255), nullable=False)
    isbn = Column(String(20), unique=True, nullable=False)
    published_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class BookSchema(BaseModel):
    """Pydantic schema for Book"""
    id: int = None
    title: str
    author: str
    isbn: str
    published_date: datetime = None
    created_at: datetime = None

    class Config:
        from_attributes = True


# Initialize database tables
def init_db():
    """Create database tables if they don't exist"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")


init_db()


def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Kubernetes liveness/readiness probes"""
    try:
        # Test database connection
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}, 503


@app.get("/books", response_model=list[BookSchema], tags=["Books"])
async def list_books(db: Session = None):
    """List all books in the catalog"""
    if not SessionLocal:
        raise HTTPException(status_code=503, detail="Database connection unavailable")

    db = SessionLocal()
    try:
        books = db.query(BookModel).all()
        return books
    except Exception as e:
        logger.error(f"Failed to list books: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve books")
    finally:
        db.close()


@app.post("/books", response_model=BookSchema, tags=["Books"])
async def create_book(book: BookSchema):
    """Create a new book in the catalog"""
    if not SessionLocal:
        raise HTTPException(status_code=503, detail="Database connection unavailable")

    db = SessionLocal()
    try:
        # Check if ISBN already exists
        existing = db.query(BookModel).filter(BookModel.isbn == book.isbn).first()
        if existing:
            raise HTTPException(status_code=400, detail="Book with this ISBN already exists")

        db_book = BookModel(
            title=book.title,
            author=book.author,
            isbn=book.isbn,
            published_date=book.published_date or datetime.utcnow()
        )
        db.add(db_book)
        db.commit()
        db.refresh(db_book)

        logger.info(f"Book created: {book.title} by {book.author}")
        return db_book
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create book: {e}")
        raise HTTPException(status_code=500, detail="Failed to create book")
    finally:
        db.close()


@app.get("/books/{book_id}", response_model=BookSchema, tags=["Books"])
async def get_book(book_id: int):
    """Get a specific book by ID"""
    if not SessionLocal:
        raise HTTPException(status_code=503, detail="Database connection unavailable")

    db = SessionLocal()
    try:
        book = db.query(BookModel).filter(BookModel.id == book_id).first()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        return book
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get book: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve book")
    finally:
        db.close()


@app.put("/books/{book_id}", response_model=BookSchema, tags=["Books"])
async def update_book(book_id: int, book_update: BookSchema):
    """Update an existing book"""
    if not SessionLocal:
        raise HTTPException(status_code=503, detail="Database connection unavailable")

    db = SessionLocal()
    try:
        book = db.query(BookModel).filter(BookModel.id == book_id).first()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        book.title = book_update.title
        book.author = book_update.author
        book.isbn = book_update.isbn
        book.published_date = book_update.published_date or datetime.utcnow()

        db.commit()
        db.refresh(book)

        logger.info(f"Book updated: {book.title}")
        return book
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update book: {e}")
        raise HTTPException(status_code=500, detail="Failed to update book")
    finally:
        db.close()


@app.delete("/books/{book_id}", tags=["Books"])
async def delete_book(book_id: int):
    """Delete a book from the catalog"""
    if not SessionLocal:
        raise HTTPException(status_code=503, detail="Database connection unavailable")

    db = SessionLocal()
    try:
        book = db.query(BookModel).filter(BookModel.id == book_id).first()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

        db.delete(book)
        db.commit()

        logger.info(f"Book deleted: ID {book_id}")
        return {"detail": "Book deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete book: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete book")
    finally:
        db.close()


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {"message": "SecureBooks API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
