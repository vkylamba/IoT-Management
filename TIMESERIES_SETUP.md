# MongoDB Time Series Collections for IoT Management

## Overview
The `RawData` and `DeviceStatus` models have been configured to use MongoDB's time series collection feature for optimized storage and querying of IoT device data.

## Configured Collections

### 1. RawData Collection
- **Collection Name**: `device_rawdata`
- **Time Field**: `data_arrival_time`
- **Meta Field**: `device_id`
- **Granularity**: seconds (optimized for high-frequency IoT data)
- **Use Case**: Stores raw sensor data from devices

### 2. DeviceStatus Collection  
- **Collection Name**: `device_devicestatus`
- **Time Field**: `created_at`
- **Meta Field**: `device_id`
- **Granularity**: hours (optimized for status updates)
- **Additional Indexes**: `name`, `user_id`
- **Use Case**: Stores device status reports and summaries

## Setup

### Option 1: Using Django Migrations (Recommended)
```bash
cd /Users/macbookpro/temp/IoT-Management/src
python manage.py migrate device
```

This will set up both collections automatically with indexes.

### Option 2: Using Management Command

#### Set up all collections:
```bash
cd /Users/macbookpro/temp/IoT-Management/src
python manage.py setup_timeseries_collection
```

#### Set up specific collection:
```bash
# For RawData only
python manage.py setup_timeseries_collection --collection rawdata

# For DeviceStatus only
python manage.py setup_timeseries_collection --collection devicestatus
```

### Option 3: Add Indexes to Existing Collections

If your time series collections already exist and you just need to add the indexes:

```bash
# Add indexes to all collections
python manage.py add_timeseries_indexes

# Add indexes to specific collection
python manage.py add_timeseries_indexes --collection rawdata
python manage.py add_timeseries_indexes --collection devicestatus
```

This command will:
- Check if each index already exists (skips duplicates)
- Create missing indexes
- Show summary of created vs skipped indexes

#### Management Command Options
- `--drop-existing`: Drop existing collection immediately (skips backup and migration)
- `--expire-after SECONDS`: Set TTL for automatic data expiration (e.g., 31536000 for 1 year)

Example with auto-expiration:
```bash
python manage.py setup_timeseries_collection --expire-after 31536000
```

**Note**: Without `--drop-existing`, the command will automatically migrate existing data and create a backup.

## Configuration

### RawData Time Series Collection
- **Time Field**: `data_arrival_time` - The timestamp when data arrives
- **Meta Field**: `device_id` - Groups data by device for efficient queries
- **Granularity**: `seconds` - Optimized for second-level precision
- **Additional Indexes**: 
  - Descending on `data_arrival_time`
  - `device` + `data_arrival_time` - For device-specific queries
  - `channel` + `data_arrival_time` - For channel-specific queries
  - `data_type` + `data_arrival_time` - For data type filtering
  - `device` + `channel` + `data_arrival_time` - For combined filters

### DeviceStatus Time Series Collection
- **Time Field**: `created_at` - The timestamp when status was created
- **Meta Field**: `device_id` - Groups status by device
- **Granularity**: `hours` - Optimized for hourly status updates
- **Additional Indexes**: 
  - `name` + `created_at` - For filtering by status name
  - `user_id` + `created_at` - For user-specific queries

## Benefits

1. **Better Performance**: Optimized for time-based queries
2. **Reduced Storage**: Automatic compression of time series data
3. **Automatic Indexing**: Built-in indexes on time field
4. **Flexible Queries**: Efficient range queries and aggregations

## Important Notes

### Existing Data Migration
If you have existing data in `device_rawdata` or `device_devicestatus` collections:
1. The migration automatically handles data migration without data loss
2. Old collections are renamed to `<collection_name>_old_YYYYMMDD_HHMMSS` as backups
3. Data is copied to new time series collections
4. You can safely delete old backups after verifying the migration

### Cleanup Old Backups

After migration, old collections are kept as backups. To clean them up:

#### List old collections:
```bash
python manage.py cleanup_old_collections --list-only
```

#### Delete all old collections (with confirmation):
```bash
python manage.py cleanup_old_collections
```

#### Delete specific collection:
```bash
python manage.py cleanup_old_collections --collection device_rawdata_old_20260214_120000
```

#### Auto-confirm deletion (no prompt):
```bash
python manage.py cleanup_old_collections --auto-confirm
```

## Verification

After running the migration, verify the collections:

```python
from pymongo import MongoClient
import os

client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("MONGODB_NAME")]

# Check RawData collection
info = db.command("listCollections", filter={"name": "device_rawdata"})
print("RawData:", info["cursor"]["firstBatch"][0])

# Check DeviceStatus collection
info = db.command("listCollections", filter={"name": "device_devicestatus"})
print("DeviceStatus:", info["cursor"]["firstBatch"][0])

# List all indexes on RawData collection
print("\nRawData Indexes:")
for index_name, index_info in db.device_rawdata.index_information().items():
    print(f"  {index_name}: {index_info['key']}")

# List all indexes on DeviceStatus collection
print("\nDeviceStatus Indexes:")
for index_name, index_info in db.device_devicestatus.index_information().items():
    print(f"  {index_name}: {index_info['key']}")
```

Expected output should show `"type": "timeseries"` for both collections and list all the configured indexes.

## Querying Time Series Data

### RawData Queries

```python
from device.models import RawData, Device
from django.utils import timezone
from datetime import timedelta

# Query last 24 hours of data
yesterday = timezone.now() - timedelta(days=1)
recent_data = RawData.objects.filter(
    data_arrival_time__gte=yesterday
).order_by('-data_arrival_time')

# Query by device
device = Device.objects.first()
device_data = RawData.objects.filter(
    device=device,
    data_arrival_time__gte=yesterday
)

# Query by channel
channel_data = RawData.objects.filter(
    channel='temperature',
    data_arrival_time__gte=yesterday
).order_by('-data_arrival_time')

# Query by data type
sensor_data = RawData.objects.filter(
    data_type='sensor_reading',
    data_arrival_time__gte=yesterday
)

# Combined query: device + channel
device_channel_data = RawData.objects.filter(
    device=device,
    channel='humidity',
    data_arrival_time__gte=yesterday
).order_by('-data_arrival_time')

# Query specific time range
start_time = timezone.now() - timedelta(hours=6)
end_time = timezone.now()
hourly_data = RawData.objects.filter(
    data_arrival_time__gte=start_time,
    data_arrival_time__lt=end_time
).order_by('data_arrival_time')
```

### DeviceStatus Queries

```python
from device.models import DeviceStatus, Device
from django.utils import timezone
from datetime import timedelta

# Query last week's status reports
week_ago = timezone.now() - timedelta(days=7)
status_reports = DeviceStatus.objects.filter(
    created_at__gte=week_ago
).order_by('-created_at')

# Query by status name
daily_status = DeviceStatus.objects.filter(
    name=DeviceStatus.DAILY_STATUS,
    created_at__gte=week_ago
)

# Query by device
device = Device.objects.first()
device_status = DeviceStatus.objects.filter(
    device=device,
    created_at__gte=week_ago
).order_by('-created_at')

# Query by user
from device.models import User
user = User.objects.first()
user_status = DeviceStatus.objects.filter(
    user=user,
    name=DeviceStatus.LAST_DAY_REPORT
).order_by('-created_at')[:30]
```

## Troubleshooting

### Migration Process
The migration automatically:
1. Detects if `device_rawdata` is a regular or time series collection
2. If regular: Creates temp collection → Copies data → Renames old to backup → Renames temp to active
3. If already time series: Skips migration
4. Keeps old data as `device_rawdata_old_YYYYMMDD_HHMMSS` for safety

### Verify Migration Success
```python
from pymongo import MongoClient
import os

client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("MONGODB_NAME")]

# Check if collection is time series
info = db.command("listCollections", filter={"name": "device_rawdata"})
coll_info = info["cursor"]["firstBatch"][0]
print(f"Type: {coll_info.get('type')}")  # Should be 'timeseries'

# Check document count
old_count = db.device_rawdata_old_20260214_120000.count_documents({})
new_count = db.device_rawdata.count_documents({})
print(f"Old: {old_count}, New: {new_count}")  # Should match
```

### Rollback if Needed
If something goes wrong, you can restore from the backup:
```bash
# In MongoDB shell or Python
db.device_rawdata.drop()
db.device_rawdata_old_20260214_120000.rename("device_rawdata")
```

### Connection Issues
Ensure your MongoDB environment variables are set:
- `MONGODB_HOST`
- `MONGODB_PORT`
- `MONGODB_NAME`
- `MONGODB_USERNAME`
- `MONGODB_PASSWORD`

## References
- [MongoDB Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/)
- [Django Migrations](https://docs.djangoproject.com/en/stable/topics/migrations/)
