"""
Migration to create MongoDB time series collection for RawData model.

This migration creates a time series collection optimized for IoT device data
with automatic data expiration and efficient time-based queries.
"""
from django.conf import settings
from django.db import migrations
from pymongo import MongoClient
from pymongo.errors import CollectionInvalid
import os
from datetime import datetime


def create_timeseries_collection(apps, schema_editor):
    """
    Create MongoDB time series collection for RawData model.
    If a non-timeseries collection exists, migrate data to a new timeseries collection.
    """
    # Get MongoDB connection details from settings
    db_name = os.getenv("MONGODB_NAME", settings.DATABASES['default']['NAME'])
    mongo_host = os.getenv("MONGODB_HOST", "localhost")
    mongo_port = int(os.getenv("MONGODB_PORT", 27017))
    mongo_username = os.getenv("MONGODB_USERNAME", "")
    mongo_password = os.getenv("MONGODB_PASSWORD", "")
    
    # Build connection URI
    if mongo_username and mongo_password:
        connection_uri = f"mongodb://{mongo_username}:{mongo_password}@{mongo_host}:{mongo_port}"
    else:
        connection_uri = f"mongodb://{mongo_host}:{mongo_port}"
    
    # Connect to MongoDB
    client = MongoClient(connection_uri)
    db = client[db_name]
    
    # Collection name following Django's naming convention: appname_modelname
    collection_name = "device_rawdata"
    temp_collection_name = f"{collection_name}_temp"
    
    try:
        # Check if collection already exists
        if collection_name in db.list_collection_names():
            # Check if it's already a time series collection
            collection_info = db.command("listCollections", filter={"name": collection_name})
            if collection_info["cursor"]["firstBatch"]:
                coll_type = collection_info["cursor"]["firstBatch"][0].get("type")
                if coll_type == "timeseries":
                    print(f"Collection '{collection_name}' already exists as a time series collection.")
                    client.close()
                    return
                else:
                    print(f"Collection '{collection_name}' exists but is not a time series collection.")
                    print(f"Migrating data to time series collection...")
                    
                    # Count existing documents
                    doc_count = db[collection_name].count_documents({})
                    print(f"Found {doc_count} documents to migrate")
                    
                    # Rename old collection first (before creating time series collection)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    old_collection_name = f"{collection_name}_old_{timestamp}"
                    print(f"Renaming old collection '{collection_name}' to '{old_collection_name}'...")
                    db[collection_name].rename(old_collection_name)
                    
                    # Create time series collection with the correct name directly
                    print(f"Creating time series collection '{collection_name}'...")
                    db.create_collection(
                        collection_name,
                        timeseries={
                            "timeField": "data_arrival_time",
                            "metaField": "device_id",
                            "granularity": "seconds"
                        }
                    )
                    
                    # Copy data from old collection to new time series collection
                    if doc_count > 0:
                        print(f"Copying {doc_count} documents in batches...")
                        batch_size = 1000
                        copied_count = 0
                        
                        # Use cursor with batch processing to avoid memory issues
                        cursor = db[old_collection_name].find().batch_size(batch_size)
                        batch = []
                        
                        for document in cursor:
                            batch.append(document)
                            
                            if len(batch) >= batch_size:
                                db[collection_name].insert_many(batch)
                                copied_count += len(batch)
                                progress = (copied_count / doc_count) * 100
                                print(f"Progress: {copied_count:,}/{doc_count:,} ({progress:.1f}%)")
                                batch = []
                        
                        # Insert remaining documents
                        if batch:
                            db[collection_name].insert_many(batch)
                            copied_count += len(batch)
                        
                        print(f"Successfully copied {copied_count:,} documents")
                    
                    print(f"Successfully migrated to time series collection '{collection_name}'")
                    print(f"  - Time field: data_arrival_time")
                    print(f"  - Meta field: device_id")
                    print(f"  - Granularity: seconds")
                    print(f"  - Migrated documents: {doc_count}")
                    print(f"")
                    print(f"⚠️  Old collection backed up as '{old_collection_name}'")
                    print(f"   To delete it, run: python manage.py cleanup_old_collections")
                    
                    client.close()
                    return
        
        # Create time series collection (if it doesn't exist)
        db.create_collection(
            collection_name,
            timeseries={
                "timeField": "data_arrival_time",
                "metaField": "device_id",  # Using device_id as metadata for efficient grouping
                "granularity": "seconds"   # Optimized for second-level granularity
            },
            # Optional: Set expiration time for old data (e.g., 1 year)
            # expireAfterSeconds=31536000
        )
        
        # Create additional indexes for common query patterns
        db[collection_name].create_index([("channel", 1), ("data_arrival_time", -1)])
        db[collection_name].create_index([("data_type", 1), ("data_arrival_time", -1)])
        db[collection_name].create_index([("device_id", 1), ("channel", 1), ("data_arrival_time", -1)])
        
        print(f"Successfully created time series collection '{collection_name}'")
        print(f"  - Time field: data_arrival_time")
        print(f"  - Meta field: device_id")
        print(f"  - Granularity: seconds")
        print(f"  - Additional indexes: channel, data_type, device_id+channel")
        
    except CollectionInvalid as e:
        print(f"Error creating collection: {e}")
    except Exception as e:
        print(f"Error during migration: {e}")
        # Cleanup: if we renamed old collection but failed, try to restore it
        old_pattern_collections = [c for c in db.list_collection_names() if c.startswith(f"{collection_name}_old_")]
        if old_pattern_collections and collection_name not in db.list_collection_names():
            # Restore the most recent backup
            latest_backup = sorted(old_pattern_collections)[-1]
            print(f"Attempting to restore '{latest_backup}' to '{collection_name}'...")
            try:
                db[latest_backup].rename(collection_name)
                print(f"Restored backup to '{collection_name}'")
            except Exception as restore_error:
                print(f"Failed to restore: {restore_error}")
    finally:
        client.close()


def drop_timeseries_collection(apps, schema_editor):
    """
    Drop the time series collection (reverse migration).
    """
    db_name = os.getenv("MONGODB_NAME", settings.DATABASES['default']['NAME'])
    mongo_host = os.getenv("MONGODB_HOST", "localhost")
    mongo_port = int(os.getenv("MONGODB_PORT", 27017))
    mongo_username = os.getenv("MONGODB_USERNAME", "")
    mongo_password = os.getenv("MONGODB_PASSWORD", "")
    
    if mongo_username and mongo_password:
        connection_uri = f"mongodb://{mongo_username}:{mongo_password}@{mongo_host}:{mongo_port}"
    else:
        connection_uri = f"mongodb://{mongo_host}:{mongo_port}"
    
    client = MongoClient(connection_uri)
    db = client[db_name]
    
    collection_name = "device_rawdata"
    
    if collection_name in db.list_collection_names():
        db.drop_collection(collection_name)
        print(f"Dropped collection '{collection_name}'")
    
    client.close()


class Migration(migrations.Migration):
    
    dependencies = [
        ('device', '0001_initial'),
    ]
    
    operations = [
        migrations.RunPython(
            create_timeseries_collection,
            reverse_code=drop_timeseries_collection
        ),
    ]
