"""
Management command to create or verify MongoDB time series collections for RawData and DeviceStatus.

Usage:
    python manage.py setup_timeseries_collection
    python manage.py setup_timeseries_collection --collection rawdata
    python manage.py setup_timeseries_collection --collection devicestatus
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from pymongo import MongoClient
from pymongo.errors import CollectionInvalid
import os
from datetime import datetime


class Command(BaseCommand):
    help = 'Create MongoDB time series collections for RawData and DeviceStatus models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--collection',
            type=str,
            choices=['rawdata', 'devicestatus', 'all'],
            default='all',
            help='Which collection to set up (rawdata, devicestatus, or all)',
        )
        parser.add_argument(
            '--drop-existing',
            action='store_true',
            help='Drop existing collection before creating time series collection',
        )
        parser.add_argument(
            '--expire-after',
            type=int,
            default=None,
            help='Set expiration time in seconds for old data (e.g., 31536000 for 1 year)',
        )

    def setup_collection(self, db, collection_config, options):
        """
        Generic method to set up a time series collection.
        """
        collection_name = collection_config['name']
        temp_collection_name = f"{collection_name}_temp"
        timeseries_config = collection_config['timeseries']
        
        # Check if collection exists
        if collection_name in db.list_collection_names():
            # Check if it's already a time series collection
            collection_info = db.command("listCollections", filter={"name": collection_name})
            if collection_info["cursor"]["firstBatch"]:
                coll_type = collection_info["cursor"]["firstBatch"][0].get("type")
                if coll_type == "timeseries":
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Collection '{collection_name}' already exists as a time series collection."
                        )
                    )
                    return True
                else:
                    if options['drop_existing']:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Dropping existing collection '{collection_name}'..."
                            )
                        )
                        db.drop_collection(collection_name)
                    else:
                        # Migrate existing data to time series collection
                        self.stdout.write(
                            self.style.WARNING(
                                f"Collection '{collection_name}' exists but is not a time series collection."
                            )
                        )
                        self.stdout.write("Migrating data to time series collection...")
                        
                        # Count existing documents
                        doc_count = db[collection_name].count_documents({})
                        self.stdout.write(f"Found {doc_count:,} documents to migrate")
                        
                        # Rename old collection first (before creating time series collection)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        old_collection_name = f"{collection_name}_old_{timestamp}"
                        self.stdout.write(f"Renaming old collection '{collection_name}' to '{old_collection_name}'...")
                        db[collection_name].rename(old_collection_name)
                        
                        # Create time series collection with the correct name directly
                        self.stdout.write(f"Creating time series collection '{collection_name}'...")
                        
                        collection_options = {"timeseries": timeseries_config}
                        
                        if options['expire_after']:
                            collection_options['expireAfterSeconds'] = options['expire_after']
                        
                        db.create_collection(collection_name, **collection_options)
                        
                        # Create additional indexes if specified
                        if 'indexes' in collection_config:
                            for index in collection_config['indexes']:
                                db[collection_name].create_index(index)
                        
                        # Copy data from old collection to new time series collection
                        if doc_count > 0:
                            self.stdout.write(f"Copying {doc_count:,} documents in batches...")
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
                                    self.stdout.write(
                                        f"  Progress: {copied_count:,}/{doc_count:,} ({progress:.1f}%)",
                                        ending='\\r'
                                    )
                                    self.stdout.flush()
                                    batch = []
                            
                            # Insert remaining documents
                            if batch:
                                db[collection_name].insert_many(batch)
                                copied_count += len(batch)
                            
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"\\n✓ Successfully copied {copied_count:,} documents"
                                )
                            )
                        
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Successfully migrated to time series collection '{collection_name}'"
                            )
                        )
                        self.stdout.write(f"  Time field: {timeseries_config['timeField']}")
                        self.stdout.write(f"  Meta field: {timeseries_config['metaField']}")
                        self.stdout.write(f"  Granularity: {timeseries_config['granularity']}")
                        self.stdout.write(f"  Migrated documents: {doc_count:,}")
                        if options['expire_after']:
                            self.stdout.write(f"  Expire after: {options['expire_after']} seconds")
                        self.stdout.write("")
                        self.stdout.write(
                            self.style.WARNING(
                                f"⚠️  Old collection backed up as '{old_collection_name}'"
                            )
                        )
                        self.stdout.write(
                            "   To delete it, run: python manage.py cleanup_old_collections"
                        )
                        
                        return True
        
        # Create time series collection
        collection_options = {"timeseries": timeseries_config}
        
        # Add expiration if specified
        if options['expire_after']:
            collection_options['expireAfterSeconds'] = options['expire_after']
        
        db.create_collection(collection_name, **collection_options)
        
        # Create additional indexes if specified
        if 'indexes' in collection_config:
            for index in collection_config['indexes']:
                db[collection_name].create_index(index)
        
        self.stdout.write(self.style.SUCCESS(f"✓ Successfully created time series collection '{collection_name}'"))
        self.stdout.write(f"  Time field: {timeseries_config['timeField']}")
        self.stdout.write(f"  Meta field: {timeseries_config['metaField']}")
        self.stdout.write(f"  Granularity: {timeseries_config['granularity']}")
        if options['expire_after']:
            self.stdout.write(f"  Expire after: {options['expire_after']} seconds")
        
        return True
    
    def handle(self, *args, **options):
        # Collection configurations
        collections_config = {
            'rawdata': {
                'name': 'device_rawdata',
                'timeseries': {
                    "timeField": "data_arrival_time",
                    "metaField": "device_id",
                    "granularity": "seconds"
                },
                'indexes': [
                    [("channel", 1), ("data_arrival_time", -1)],
                    [("data_type", 1), ("data_arrival_time", -1)],
                    [("device_id", 1), ("channel", 1), ("data_arrival_time", -1)]
                ]
            },
            'devicestatus': {
                'name': 'device_devicestatus',
                'timeseries': {
                    "timeField": "created_at",
                    "metaField": "device_id",
                    "granularity": "hours"
                },
                'indexes': [
                    [("name", 1), ("created_at", -1)],
                    [("user_id", 1), ("created_at", -1)]
                ]
            }
        }
        
        # Get MongoDB connection details
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
        
        try:
            # Connect to MongoDB
            client = MongoClient(connection_uri)
            db = client[db_name]
            
            # Determine which collections to set up
            if options['collection'] == 'all':
                collections_to_setup = ['rawdata', 'devicestatus']
            else:
                collections_to_setup = [options['collection']]
            
            self.stdout.write(
                self.style.WARNING(
                    f"\\nSetting up {len(collections_to_setup)} time series collection(s)...\\n"
                )
            )
            
            success_count = 0
            for coll_key in collections_to_setup:
                self.stdout.write(f"\\n{'='*60}")
                self.stdout.write(f"Processing: {collections_config[coll_key]['name']}")
                self.stdout.write(f"{'='*60}\\n")
                
                try:
                    if self.setup_collection(db, collections_config[coll_key], options):
                        success_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"✗ Error setting up {coll_key}: {e}"))
            
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"\\n✓ Successfully set up {success_count}/{len(collections_to_setup)} collection(s)"
                )
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Unexpected error: {e}"))
        finally:
            client.close()
