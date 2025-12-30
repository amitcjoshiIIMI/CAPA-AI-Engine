import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms, models
from torch.utils.data import DataLoader
import json
import os
from pathlib import Path

def train_resnet18(data_dir, output_dir, epochs=10):
    """
    Train ResNet-18 on NEU Metal Surface Defects Dataset
    Classes are automatically derived from folder structure
    """
    
    # Define transforms
    train_transform = transforms.Compose([
        transforms.Resize(256),
        transforms.RandomCrop(224),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    
    val_transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    
    # Load datasets - ImageFolder automatically creates classes from subdirectories
    train_dataset = datasets.ImageFolder(
        root=os.path.join(data_dir, 'train'),  # ← lowercase
        transform=train_transform
    )
    
    val_dataset = datasets.ImageFolder(
        root=os.path.join(data_dir, 'valid'),  # ← lowercase
        transform=val_transform
    )
    
    # Extract class names (sorted alphabetically by ImageFolder)
    class_names = train_dataset.classes
    num_classes = len(class_names)
    
    print(f"📊 Detected {num_classes} classes: {class_names}")
    
    # Create data loaders
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True, num_workers=4)
    val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False, num_workers=4)
    
    # Initialize model
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"🖥️  Using device: {device}")
    
    model = models.resnet18(pretrained=True)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    model = model.to(device)
    
    # Training setup
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    # Training loop
    best_acc = 0.0
    for epoch in range(epochs):
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
        
        # Validation
        model.eval()
        correct = 0
        total = 0
        
        with torch.no_grad():
            for inputs, labels in val_loader:
                inputs, labels = inputs.to(device), labels.to(device)
                outputs = model(inputs)
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()
        
        val_acc = 100 * correct / total
        print(f'Epoch {epoch+1}/{epochs} - Loss: {running_loss/len(train_loader):.4f} - Val Acc: {val_acc:.2f}%')
        
        if val_acc > best_acc:
            best_acc = val_acc
            # Save model weights
            torch.save(model.state_dict(), os.path.join(output_dir, 'resnet18_capa.pth'))
            print(f'✅ Saved best model with accuracy: {best_acc:.2f}%')
    
    # Save metadata (class names and model config)
    metadata = {
        'class_names': class_names,
        'num_classes': num_classes,
        'model_architecture': 'resnet18',
        'input_size': [224, 224],
        'normalization': {
            'mean': [0.485, 0.456, 0.406],
            'std': [0.229, 0.224, 0.225]
        }
    }
    
    with open(os.path.join(output_dir, 'model_metadata.json'), 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n✅ Training complete!")
    print(f"📁 Model saved to: {output_dir}/resnet18_capa.pth")
    print(f"📄 Metadata saved to: {output_dir}/model_metadata.json")
    print(f"📊 Classes: {class_names}")
    print(f"🎯 Best validation accuracy: {best_acc:.2f}%")

if __name__ == "__main__":
    # Paths with spaces in folder name
    DATA_DIR = "./data/NEU Metal Surface Defects Data"  # ← Correct path
    OUTPUT_DIR = "./models"
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    train_resnet18(DATA_DIR, OUTPUT_DIR, epochs=10)
