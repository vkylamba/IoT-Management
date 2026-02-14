"""
Management command to add indexes to existing MongoDB time series collections.

Usage:
    python manage.py add_timeseries_indexes
    python manage.py add_timeseries_indexes --collection rawdata
    python manage.py add_timeseries_indexes --collection devicestatus
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from pymongo import MongoClient
import os


class Command(BaseCommand):
    help = 'Add indexes to existing MongoDB time series collections'

    def add_arguments(self, parser):
        parser.add_argument(
            '--collection',
            type=str,
            choices=['rawdata', 'devicestatus', 'all'],
            default='all',
            help='Which collection to add indexes to (rawdata, devicestatus, or all)',
        )

    def add_indexes_to_collection(self, db, collection_name, indexes, description):
        """
        Add indexes to a collection.
        """
        if collection_name not in db.list_collection_names():
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  Collection '{collection_name}' does not exist. Skipping."
                )
            )
            return False
        
        self.stdout.write(f"Adding indexes to '{collection_name}'...")
        
        # Get existing indexes
        existing_indexes = db[collection_name].index_information()
        
        created_count = 0
        skipped_count = 0
        
        for index_spec in indexes:
            # Create a name for the index based on fields
            index_name = "_".join([f"{field}_{direction}" for field, direction in index_spec])
            
            # Check if index already exists
            index_exists = False
            for existing_name, existing_info in existing_indexes.items():
                if existing_info.get('key') == index_spec:
                    index_exists = True
                    break
            
            if index_exists:
                self.stdout.write(f"  ↷ Index already exists: {index_name}")
                skipped_count += 1
            else:
                try:
                    db[collection_name].create_index(index_spec, name=index_name)
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ Created index: {index_name}")
                    )
                    created_count += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"  ✗ Failed to create index {index_name}: {e}")
                    )
        
        self.stdout.write("")
        self.stdout.write(
            f"Summary for '{collection_name}': {created_count} created, {skipped_count} skipped"
        )
        
        return True

    def handle(self, *args, **options):
        # Index configurations
        indexes_config = {
            'rawdata': {
                'name': 'device_rawdata',
                'description': 'RawData collection',
                'indexes': [
                    [("channel", 1), ("data_arrival_time", -1)],
                    [("data_type", 1), ("data_arrival_time", -1)],
                    [("device_id", 1), ("channel", 1), ("data_arrival_time", -1)]
                ]
            },
            'devicestatus': {
                'name': 'device_devicestatus',
                'description': 'DeviceStatus collection',
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
            
            # Determine which collections to process
            if options['collection'] == 'all':
                collections_to_process = ['rawdata', 'devicestatus']
            else:
                collections_to_process = [options['collection']]
            
            self.stdout.write(
                self.style.WARNING(
                    f"\nAdding indexes to {len(collections_to_process)} collection(s)...\n"
                )
            )
            
            success_count = 0
            for coll_key in collections_to_process:
                config = indexes_config[coll_key]
                self.stdout.write(f"\n{'='*60}")
                self.stdout.write(f"Processing: {config['name']} ({config['description']})")
                self.stdout.write(f"{'='*60}\n")
                
                try:
                    if self.add_indexes_to_collection(
                        db, 
                        config['name'], 
                        config['indexes'],
                        config['description']
                    ):
                        success_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"✗ Error processing {coll_key}: {e}"))
            
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Successfully processed {success_count}/{len(collections_to_process)} collection(s)"
                )
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Unexpected error: {e}"))
        finally:
            client.close()
