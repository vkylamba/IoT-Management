"""
Management command to cleanup old MongoDB collections that were backed up during migration.

Usage:
    python manage.py cleanup_old_collections
    python manage.py cleanup_old_collections --list-only
    python manage.py cleanup_old_collections --collection device_rawdata_old_20260214_120000
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from pymongo import MongoClient
import os
import re


class Command(BaseCommand):
    help = 'Cleanup old MongoDB collections that were backed up during time series migration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--list-only',
            action='store_true',
            help='Only list old collections without prompting for deletion',
        )
        parser.add_argument(
            '--collection',
            type=str,
            help='Specific collection name to delete (skips confirmation prompt)',
        )
        parser.add_argument(
            '--auto-confirm',
            action='store_true',
            help='Automatically confirm deletion without prompting',
        )

    def handle(self, *args, **options):
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
            
            # Pattern to match old collections (e.g., device_rawdata_old_20260214_120000)
            old_collection_pattern = re.compile(r'^.*_old_\d{8}_\d{6}$')
            
            # Find all old collections
            all_collections = db.list_collection_names()
            old_collections = [
                col for col in all_collections 
                if old_collection_pattern.match(col)
            ]
            
            if not old_collections:
                self.stdout.write(self.style.SUCCESS("✓ No old collections found."))
                client.close()
                return
            
            # Display found collections
            self.stdout.write(self.style.WARNING(f"\nFound {len(old_collections)} old collection(s):"))
            self.stdout.write("")
            
            for col in old_collections:
                doc_count = db[col].count_documents({})
                # Extract date from collection name
                match = re.search(r'_old_(\d{8})_(\d{6})', col)
                if match:
                    date_str = match.group(1)
                    time_str = match.group(2)
                    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
                    self.stdout.write(f"  • {col}")
                    self.stdout.write(f"    Created: {formatted_date}")
                    self.stdout.write(f"    Documents: {doc_count:,}")
                    self.stdout.write("")
            
            # If list-only mode, exit
            if options['list_only']:
                client.close()
                return
            
            # If specific collection specified
            if options['collection']:
                if options['collection'] not in old_collections:
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ Collection '{options['collection']}' not found or not an old backup collection."
                        )
                    )
                    client.close()
                    return
                
                collections_to_delete = [options['collection']]
            else:
                collections_to_delete = old_collections
            
            # Confirm deletion
            if not options['auto_confirm']:
                self.stdout.write(
                    self.style.WARNING(
                        f"\n⚠️  You are about to delete {len(collections_to_delete)} collection(s)."
                    )
                )
                self.stdout.write("This action cannot be undone!\n")
                
                response = input("Type 'yes' to confirm deletion: ")
                if response.lower() != 'yes':
                    self.stdout.write(self.style.WARNING("Deletion cancelled."))
                    client.close()
                    return
            
            # Delete collections
            self.stdout.write("\nDeleting collections...")
            for col in collections_to_delete:
                doc_count = db[col].count_documents({})
                db[col].drop()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Deleted '{col}' ({doc_count:,} documents)"
                    )
                )
            
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Successfully deleted {len(collections_to_delete)} collection(s)"
                )
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error: {e}"))
        finally:
            client.close()
