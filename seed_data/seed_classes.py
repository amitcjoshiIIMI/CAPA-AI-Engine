import boto3
import json
from datetime import datetime

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Get table name
client = boto3.client('dynamodb', region_name='us-east-1')
tables = client.list_tables()['TableNames']
class_table_name = [t for t in tables if 'ClassRegistry' in t][0]

table = dynamodb.Table(class_table_name)

# Original 6 classes
ORIGINAL_CLASSES = [
    {
        'class_name': 'Crazing',
        'description': 'Fine cracks on the surface caused by thermal or mechanical stress',
        'created_at': datetime.now().isoformat(),
        'is_original': True,
        'image_count': 0
    },
    {
        'class_name': 'Inclusion',
        'description': 'Foreign particles embedded in the material during manufacturing',
        'created_at': datetime.now().isoformat(),
        'is_original': True,
        'image_count': 0
    },
    {
        'class_name': 'Patches',
        'description': 'Uneven coating or surface irregularities',
        'created_at': datetime.now().isoformat(),
        'is_original': True,
        'image_count': 0
    },
    {
        'class_name': 'Pitted_Surface',
        'description': 'Small holes or depressions on the surface from corrosion',
        'created_at': datetime.now().isoformat(),
        'is_original': True,
        'image_count': 0
    },
    {
        'class_name': 'Rolled-in_Scale',
        'description': 'Oxide scale embedded into the surface during rolling',
        'created_at': datetime.now().isoformat(),
        'is_original': True,
        'image_count': 0
    },
    {
        'class_name': 'Scratches',
        'description': 'Linear marks on the surface from mechanical damage',
        'created_at': datetime.now().isoformat(),
        'is_original': True,
        'image_count': 1  # We have 1 approved image in Scratches
    }
]

print(f"Seeding {len(ORIGINAL_CLASSES)} classes into {class_table_name}...")

for cls in ORIGINAL_CLASSES:
    table.put_item(Item=cls)
    print(f"✓ Added {cls['class_name']}")

print("\nDone! Verify with:")
print(f"aws dynamodb scan --table-name {class_table_name} --query 'Items[*].[class_name.S, description.S]' --output table")