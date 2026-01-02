from database import engine
from orm import Base

Base.metadata.create_all(bind=engine)
print("Tables created")