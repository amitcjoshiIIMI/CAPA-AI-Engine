import argparse
import json
import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms, models
from PIL import Image
import boto3
from pathlib import Path

# Parse SageMaker arguments
parser = argparse.ArgumentParser()
parser.add_argument('--epochs', type=int, default=10)
parser.add_argument('--batch_size', type=int, default=32)
parser.add_argument('--learning_rate', type=float, default=0.001)
parser.add_argument('--model_dir', type=str, default=os.environ.get('SM_MODEL_DIR', '/opt/ml/model'))
parser.add_argument('--train', type=str, default=os.environ.get('SM_CHANNEL_TRAIN', '/opt/ml/input/data/train'))
parser.add_argument('--test', type=str, default=os.environ.get('SM_CHANNEL_TEST', '/opt/ml/input/data/test'))
args, unknown = parser.parse_known_args()  # Changed: ignore unknown args

print(f"Training config: epochs={args.epochs}, batch_size={args.batch_size}, lr={args.learning_rate}")


class DefectDataset(Dataset):
    """Dataset for defect images organized in class folders"""
    def __init__(self, root_dir, transform=None):
        self.root_dir = Path(root_dir)
        self.transform = transform
        self.images = []
        self.labels = []
        self.class_names = sorted([d.name for d in self.root_dir.iterdir() if d.is_dir()])
        self.class_to_idx = {cls: idx for idx, cls in enumerate(self.class_names)}
        
        # Load all images
        for class_name in self.class_names:
            class_dir = self.root_dir / class_name
            for img_path in class_dir.glob('*.bmp'):
                self.images.append(str(img_path))
                self.labels.append(self.class_to_idx[class_name])
        
        print(f"Loaded {len(self.images)} images across {len(self.class_names)} classes")
        for cls in self.class_names:
            count = sum(1 for l in self.labels if l == self.class_to_idx[cls])
            print(f"  {cls}: {count} images")
    
    def __len__(self):
        return len(self.images)
    
    def __getitem__(self, idx):
        img_path = self.images[idx]
        label = self.labels[idx]
        
        image = Image.open(img_path).convert('RGB')
        
        if self.transform:
            image = self.transform(image)
        
        return image, label


def train_model():
    """Main training function"""
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    # Data transforms with augmentation
    train_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    test_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    # Load datasets
    train_dataset = DefectDataset(args.train, transform=train_transform)
    test_dataset = DefectDataset(args.test, transform=test_transform)
    
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=2)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False, num_workers=2)
    
    # Model
    num_classes = len(train_dataset.class_names)
    model = models.resnet18(pretrained=True)
    
    # Transfer learning: freeze early layers
    for param in model.parameters():
        param.requires_grad = False
    
    # Only train final layer
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    model = model.to(device)
    
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.fc.parameters(), lr=args.learning_rate)
    
    # Training loop
    best_accuracy = 0.0
    
    for epoch in range(args.epochs):
        model.train()
        running_loss = 0.0
        
        for inputs, labels in train_loader:
            inputs, labels = inputs.to(device), labels.to(device)
            
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
        
        # Evaluation
        model.eval()
        correct = 0
        total = 0
        
        with torch.no_grad():
            for inputs, labels in test_loader:
                inputs, labels = inputs.to(device), labels.to(device)
                outputs = model(inputs)
                _, predicted = torch.max(outputs, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()
        
        accuracy = 100 * correct / total
        print(f"Epoch {epoch+1}/{args.epochs} - Loss: {running_loss/len(train_loader):.4f} - Test Accuracy: {accuracy:.2f}%")
        
        if accuracy > best_accuracy:
            best_accuracy = accuracy
    
    # Save model
    torch.save(model.state_dict(), os.path.join(args.model_dir, 'model.pth'))
    
    # Save metadata
    metadata = {
        'class_names': train_dataset.class_names,
        'num_classes': num_classes,
        'accuracy': best_accuracy,
        'epochs': args.epochs
    }
    
    with open(os.path.join(args.model_dir, 'model_metadata.json'), 'w') as f:
        json.dump(metadata, f)
    
    print(f"Training complete! Best accuracy: {best_accuracy:.2f}%")
    print(f"Model saved to {args.model_dir}")


if __name__ == '__main__':
    train_model()