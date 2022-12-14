# -*- coding: utf-8 -*-
"""LSTM for text classification

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1Hu07JSWMxiKaeUfLSB-0481o0bmy_Npl
"""

!pip install torchtext==0.10.0

!pip install Unicode

import spacy 

spacy.cli.download("en_core_web_sm")

!wget http://nlp.stanford.edu/data/glove.6B.zip
!unzip glove*.zip

import os
import pandas as pd
import numpy as np
import matplotlib as plt
from sklearn.model_selection import train_test_split
import time
import torch
import torchtext
from torchtext.legacy.data import Field, TabularDataset, BucketIterator, Iterator
import torch.nn as nn
import nltk
import spacy
#import pyprind

class DataSet(torch.utils.data.Dataset):
  def __init__(self,PATH,batch_size=32):
    super(DataSet,self).__init__()
    self.PATH = PATH
    self.batch_size = batch_size
    self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    self.spacy = spacy.load('en_core_web_sm')
    self.TEXT = torchtext.legacy.data.Field(sequential = True, tokenize = "spacy")
    self.LABEL = torchtext.legacy.data.LabelField(dtype=torch.long, sequential=False)
    self.initData()     
    self.initEmbed()    
    self.makeData()     

  def initData(self):
    DATA = os.path.join(self.PATH, 'inputs/')
    self.train_data, self.valid_data, self.test_data = torchtext.legacy.data.TabularDataset.splits(path = DATA, 
                                                                                                   train="train.csv", valid="valid.csv", test="test.csv", 
                                                                                                   format="csv", skip_header=True,
                                                                                                   fields=[('Text',self.TEXT),('label',self.LABEL)])
  def initEmbed(self):
   EMBED = os.path.join(self.PATH, "glove.840B.300d.txt")  
   self.TEXT.build_vocab(self.train_data,vectors=torchtext.vocab.Vectors(EMBED),max_size=20000,min_freq=10)
   self.LABEL.build_vocab(self.train_data)
  
  def makeData(self):
    self.train_iterator, self.valid_iterator, self.test_iterator = torchtext.legacy.data.BucketIterator.splits((self.train_data,self.valid_data,self.test_data),
                                                                                                               sort_key=lambda x: len(x.Text),    #to sort based on length
                                                                                                               batch_size=self.batch_size,device=self.device)
    #bucketiterator splits data into subgroups of texts with similar length
  def lengthData(self):
    return len(self.train_data), len(self.valid_data), len(self.test_data)
  
  def lengthVocab(self):
    return len(self.TEXT.vocab), len(self.LABEL.vocab)
  
  def freqLABEL(self):
    return self.LABEL.vocab.freqs
  
  def getData(self):
    return self.train_iterator, self.valid_iterator, self.test_iterator

  def getEmbeddings(self):
    return self.TEXT.vocab.vectors

class LSTM(torch.nn.Module):
  def __init__(self, input_dim,embedding_dim, num_layers,hidden_dim,static=False,dropout=0.2):
    super(LSTM,self).__init__()
    self.hidden_dim = hidden_dim
    self.dropout = torch.nn.Dropout(p=dropout)
    self.embedding = torch.nn.Embedding(input_dim,embedding_dim)
    if static:
      self.embedding.weight.requires_grad = False
    
    self.lstm = nn.LSTM(embedding_dim,hidden_dim, num_layers=num_layers, bidirectional=True,dropout=dropout,batch_first=True)

    self.linear = nn.Linear(hidden_dim*num_layers*2,1)

  def forward(self,text):
    embedded = self.embedding(text)
    embedded = torch.transpose(embedded, dim0=1, dim1=0)
    lstm_out, (hidden,cell) = self.lstm(embedded)
    out = self.linear(self.dropout(torch.cat([cell[i,:,:] for i in range(cell.shape[0])],dim=1)))
    return out

PATH = %pwd     #to get current path
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

df = pd.read_csv("Data.csv")
df.loc[df['Category']=='ham','Category']=0
df.loc[df['Category']=='spam','Category']=1
df['label']=df['Category']
df['Text']=df['Message']
del df['Category']
del df['Message']
print(df)

spam = df.loc[df['label']==1]
ham = df.loc[df['label']==0]
test_sp = spam[:125]
test_ham = ham[:805]
valid_sp = spam[125:250]
valid_ham = ham[805:1610]
train_sp = spam[250:]
train_ham = ham[1610:]
train = pd.concat([train_sp,train_ham],axis=0)
test = pd.concat([test_sp,test_ham],axis=0)
valid = pd.concat([valid_sp,valid_ham],axis=0)
print(train)

!mkdir inputs
train.to_csv(os.path.join(PATH,'inputs/train.csv'),index=False)
test.to_csv(os.path.join(PATH,'inputs/test.csv'),index=False)
valid.to_csv(os.path.join(PATH,'inputs/valid.csv'),index=False)

data = DataSet(PATH,32)
train_iterator,test_iterator,valid_iterator = data.getData()
embed = data.getEmbeddings()
input_dim = data.lengthVocab()[0]
embedding_dim = 300
hidden_dim = 374
output_dim = 2
num_layers = 2
batch_size = 32

model = LSTM(input_dim,embedding_dim,hidden_dim,num_layers)
model.embedding.weight.data = embed.to(device)
optimizer = torch.optim.SGD(model.parameters(),lr=0.0001)
criterion = nn.BCEWithLogitsLoss()
model=model.to(device)
criterion=criterion.to(device)

epoch_train_losses = []
epoch_test_losses = []
epoch_val_losses = []
accu_train_epoch = []
accu_test_epoch = []
accu_val_epoch = []

def binary_accuracy(preds,y):
  preds=torch.sigmoid(preds)
  preds=torch.round(preds)    #rounds off to int(0 or 1)

  correct=(preds==y).float()
  acc = correct.sum()/float(len(correct))
  return acc

def train(model,iterator,optimizer,criterion):
  train_loss_batch = []
  acc_train_batch = []
  model.train()
 # bar = pyprind.ProgBar(len(iterator), bar_char='???')      #just for knowing the progress of the loop
  for batch in iterator:
    optimizer.zero_grad()
    predictions=model.forward(batch.Text).view(-1)
    batch.label = (batch.label).type_as(predictions)
    train_loss = criterion(predictions,batch.label)
    acc = binary_accuracy(predictions,batch.label)

    train_loss.backward()
    optimizer.step()

    train_loss_batch.append(train_loss)
    acc_train_batch.append(acc)
    #bar.update()
  
  epoch_train_losses.append(sum(train_loss_batch)/len(iterator))
  accu_train_epoch.append(sum(acc_train_batch)/len(iterator))

  return epoch_train_losses[-1], accu_train_epoch[-1]

def evaluate(model,iterator,criterion):
  val_loss_batch=[]
  acc_val_batch=[]
  with torch.no_grad():
    #bar = pyprind.ProgBar(len(iterator), bar_char='???')
    for batch in iterator:
      predictions = model.forward(batch.Text).view(-1)
      batch.label = (batch.label).type_as(predictions)
      val_loss = criterion(predictions,batch.label)
      acc = binary_accuracy(predictions,batch.label)

      val_loss_batch.append(val_loss)
      acc_val_batch.append(acc)
      #bar.update()
    
    epoch_val_losses.append(sum(val_loss_batch)/len(iterator))
    accu_val_epoch.append(sum(acc_val_batch)/len(iterator))

  return epoch_val_losses[-1], accu_val_epoch[-1]

epochs = 2
for epoch in range(epochs):
  train_loss, train_acc = train(model, train_iterator, optimizer, criterion)
  valid_loss, valid_acc = evaluate(model, valid_iterator, criterion)

  print(f'| Epoch: {epoch+1:02} | Train Loss: {train_loss:.3f} | Train Acc: {train_acc*100:.2f}% | Val. Loss: {valid_loss:.3f} | Val. Acc: {valid_acc*100:.2f}% |')