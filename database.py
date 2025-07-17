import os
import base64
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base
from sqlalchemy.sql import func
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Argon2 hasher
ph = PasswordHasher()

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///fyers_auth.db')
PEPPER = os.getenv('API_KEY_PEPPER', 'default-pepper-change-in-production')

# Setup Fernet encryption for auth tokens
def get_encryption_key():
    """Generate a Fernet key from the pepper"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'fyers_static_salt',
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(PEPPER.encode()))
    return Fernet(key)

# Initialize Fernet cipher
fernet = get_encryption_key()

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=10
)

db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(255), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    is_active = Column(Boolean, default=True)

    def set_password(self, password):
        """Set password using Argon2 hashing"""
        peppered_password = password + PEPPER
        self.password_hash = ph.hash(peppered_password)

    def check_password(self, password):
        """Check password using Argon2 verification"""
        peppered_password = password + PEPPER
        try:
            ph.verify(self.password_hash, peppered_password)
            return True
        except VerifyMismatchError:
            return False

class Auth(Base):
    __tablename__ = 'auth'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    auth = Column(Text, nullable=False)  # Encrypted auth token
    broker = Column(String(20), nullable=False, default='fyers')
    user_id = Column(String(255), nullable=True)
    api_key = Column(Text, nullable=True)  # Encrypted API key
    api_secret = Column(Text, nullable=True)  # Encrypted API secret
    is_revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    
    # Check if we need to add new columns to existing auth table
    try:
        # Try to query with new columns to see if they exist
        db_session.execute("SELECT api_key, api_secret FROM auth LIMIT 1")
    except Exception as e:
        if "no such column" in str(e):
            print("Adding new columns to auth table...")
            try:
                db_session.execute("ALTER TABLE auth ADD COLUMN api_key TEXT")
                db_session.execute("ALTER TABLE auth ADD COLUMN api_secret TEXT")
                db_session.commit()
                print("Successfully added api_key and api_secret columns")
            except Exception as alter_error:
                print(f"Error adding columns: {alter_error}")
    
    # Create default admin user if not exists
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        admin_user = User(username='admin', email='admin@fyers.com')
        admin_user.set_password('admin123')  # Change this in production
        db_session.add(admin_user)
        db_session.commit()
        print("Created default admin user (username: admin, password: admin123)")

def encrypt_token(token):
    """Encrypt auth token"""
    if not token:
        return ''
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token):
    """Decrypt auth token"""
    if not encrypted_token:
        return ''
    try:
        return fernet.decrypt(encrypted_token.encode()).decode()
    except Exception as e:
        print(f"Error decrypting token: {e}")
        return None

def upsert_auth(name, auth_token, broker='fyers', user_id=None, api_key=None, api_secret=None, revoke=False):
    """Store encrypted auth token, API key, and API secret"""
    encrypted_token = encrypt_token(auth_token)
    encrypted_api_key = encrypt_token(api_key) if api_key else None
    encrypted_api_secret = encrypt_token(api_secret) if api_secret else None
    
    auth_obj = Auth.query.filter_by(name=name).first()
    if auth_obj:
        auth_obj.auth = encrypted_token
        auth_obj.broker = broker
        auth_obj.user_id = user_id
        auth_obj.api_key = encrypted_api_key
        auth_obj.api_secret = encrypted_api_secret
        auth_obj.is_revoked = revoke
    else:
        auth_obj = Auth(
            name=name, 
            auth=encrypted_token, 
            broker=broker, 
            user_id=user_id,
            api_key=encrypted_api_key,
            api_secret=encrypted_api_secret,
            is_revoked=revoke
        )
        db_session.add(auth_obj)
    db_session.commit()
    return auth_obj.id

def get_auth_token(name):
    """Get decrypted auth token"""
    try:
        auth_obj = Auth.query.filter_by(name=name).first()
        if auth_obj and not auth_obj.is_revoked:
            return decrypt_token(auth_obj.auth)
        return None
    except Exception as e:
        print(f"Error while querying the database for auth token: {e}")
        return None

def get_api_credentials(name):
    """Get decrypted API key and secret"""
    try:
        auth_obj = Auth.query.filter_by(name=name).first()
        if auth_obj and not auth_obj.is_revoked:
            api_key = decrypt_token(auth_obj.api_key) if auth_obj.api_key else None
            api_secret = decrypt_token(auth_obj.api_secret) if auth_obj.api_secret else None
            return api_key, api_secret
        return None, None
    except Exception as e:
        print(f"Error while querying the database for API credentials: {e}")
        return None, None

def get_auth_data(name):
    """Get all auth data for a user"""
    try:
        auth_obj = Auth.query.filter_by(name=name).first()
        if auth_obj and not auth_obj.is_revoked:
            return {
                'auth_token': decrypt_token(auth_obj.auth),
                'api_key': decrypt_token(auth_obj.api_key) if auth_obj.api_key else None,
                'api_secret': decrypt_token(auth_obj.api_secret) if auth_obj.api_secret else None,
                'broker': auth_obj.broker,
                'user_id': auth_obj.user_id
            }
        return None
    except Exception as e:
        print(f"Error while querying the database for auth data: {e}")
        return None

def authenticate_user(username, password):
    """Authenticate user with username and password"""
    try:
        user = User.query.filter_by(username=username, is_active=True).first()
        if user and user.check_password(password):
            return True
        return False
    except Exception as e:
        print(f"Error during authentication: {e}")
        return False

def find_user_by_username(username=None):
    """Find user by username, or return first user if no username provided"""
    try:
        if username:
            return User.query.filter_by(username=username, is_active=True).first()
        else:
            return User.query.filter_by(is_active=True).first()
    except Exception as e:
        print(f"Error finding user: {e}")
        return None