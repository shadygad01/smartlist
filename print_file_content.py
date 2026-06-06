#!/usr/bin/env python3
"""طباعة محتوى الملف بالكامل للفحص"""
import os

file_path = "open_positions.json"

print("\n" + "="*90)
print(f"📄 محتوى الملف: {file_path}")
print("="*90)

if not os.path.exists(file_path):
    print(f"❌ الملف لا يوجد!")
    exit(1)

size = os.path.getsize(file_path)
print(f"\n📊 معلومات الملف:")
print(f"   الحجم: {size} بايت")
print(f"   المسار: {os.path.abspath(file_path)}")

if size == 0:
    print(f"\n❌ الملف فارغ تماماً!")
    print("   هذه هي المشكلة الحقيقية!")
    exit(1)

print(f"\n📝 محتوى الملف:")
print("-"*90)

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

print(content)

print("\n" + "="*90)
