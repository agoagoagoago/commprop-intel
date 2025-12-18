"""
Database models and setup for CommProp Intel Map.
"""
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, Date, Text, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, date
import os

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "commprop.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# SQLAlchemy setup
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Listing(Base):
    """Property listing model."""
    __tablename__ = "listings"
    
    id = Column(String, primary_key=True)  # Hash of raw_text + first_seen_date
    property_name = Column(String, nullable=True)
    address = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    property_type = Column(String, nullable=True)  # Factory/Warehouse, Office, Shop
    property_subtype = Column(String, nullable=True)  # B1, B2, etc.
    transaction_type = Column(String, nullable=True)  # Sale, Rent
    price = Column(Integer, nullable=True)
    price_type = Column(String, nullable=True)  # total, per_sqft, per_month
    gfa_sqft = Column(Integer, nullable=True)
    lease_type = Column(String, nullable=True)  # Freehold, 999yr, 99yr, 60yr
    lease_balance_years = Column(Integer, nullable=True)
    features = Column(Text, nullable=True)  # JSON array as string
    contact_name = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    is_owner = Column(Boolean, default=False)
    is_agent = Column(Boolean, default=False)
    agency_name = Column(String, nullable=True)
    cobroke_allowed = Column(Boolean, nullable=True)
    raw_text = Column(Text, nullable=False)
    category = Column(String, nullable=True)  # Original category from website
    first_seen_date = Column(Date, default=date.today)
    last_seen_date = Column(Date, default=date.today)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    snapshots = relationship("ListingSnapshot", back_populates="listing")
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "property_name": self.property_name,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "property_type": self.property_type,
            "property_subtype": self.property_subtype,
            "transaction_type": self.transaction_type,
            "price": self.price,
            "price_type": self.price_type,
            "gfa_sqft": self.gfa_sqft,
            "lease_type": self.lease_type,
            "lease_balance_years": self.lease_balance_years,
            "features": self.features,
            "contact_name": self.contact_name,
            "contact_phone": self.contact_phone,
            "is_owner": self.is_owner,
            "is_agent": self.is_agent,
            "agency_name": self.agency_name,
            "cobroke_allowed": self.cobroke_allowed,
            "raw_text": self.raw_text,
            "category": self.category,
            "first_seen_date": self.first_seen_date.isoformat() if self.first_seen_date else None,
            "last_seen_date": self.last_seen_date.isoformat() if self.last_seen_date else None,
        }


class ListingSnapshot(Base):
    """Daily snapshot for trend tracking."""
    __tablename__ = "listing_snapshots"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False)
    seen_date = Column(Date, default=date.today)
    price = Column(Integer, nullable=True)
    raw_text = Column(Text, nullable=True)
    
    listing = relationship("Listing", back_populates="snapshots")


class Advertiser(Base):
    """Track advertisers by phone number."""
    __tablename__ = "advertisers"
    
    phone = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    is_owner = Column(Boolean, default=False)
    is_agent = Column(Boolean, default=False)
    agency_name = Column(String, nullable=True)
    total_listings = Column(Integer, default=0)
    first_seen = Column(Date, default=date.today)
    last_seen = Column(Date, default=date.today)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            "phone": self.phone,
            "name": self.name,
            "is_owner": self.is_owner,
            "is_agent": self.is_agent,
            "agency_name": self.agency_name,
            "total_listings": self.total_listings,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


class ScrapeLog(Base):
    """Log of scrape runs."""
    __tablename__ = "scrape_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    scrape_date = Column(DateTime, default=datetime.utcnow)
    listings_found = Column(Integer, default=0)
    listings_new = Column(Integer, default=0)
    listings_updated = Column(Integer, default=0)
    status = Column(String, default="pending")  # pending, running, completed, failed
    error_message = Column(Text, nullable=True)


def init_db():
    """Initialize the database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Initialize on import
init_db()
