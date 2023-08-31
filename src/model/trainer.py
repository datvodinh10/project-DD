from src.utils.vocab import Vocabulary
from src.utils.generator import OCRDataset
from src.utils.transform import Transform
from src.model.model import OCRTransformerModel
from src.utils.statistic import Statistic
from src.utils.progress_bar import CustomProgressBar
from src.utils.lr_scheduler import CosineAnnealingWarmupRestarts
from torch.utils.data import DataLoader
import torch
import torch.nn as nn
import time
import math

class Trainer:
    def __init__(self,
                 config,
                 IMAGE_PATH = None,
                 TARGET_PATH = None):
    
        self.config     = config
        self.vocabulary = Vocabulary(data_path   = TARGET_PATH,
                                     device      = config['device'])
        self.dataset    = OCRDataset(root_dir    = IMAGE_PATH,
                                     device      = config['device'],
                                     transform   = Transform(t_type=config['preprocessing']),
                                     target_dict = self.vocabulary.target_dict)
        
        self.dataloader = DataLoader(dataset     = self.dataset,
                                     batch_size  = config['batch_size'],
                                     shuffle     = True)
        
        self.len_loader = len(self.dataloader)
        self.model      = OCRTransformerModel(config,self.vocabulary.vocab_size)
        self.stat       = Statistic()
        self.criterion  = nn.CrossEntropyLoss()
        self.optimizer  = torch.optim.AdamW(self.model.parameters(),lr=config['lr'])
        self.pro_bar    = CustomProgressBar(config['num_epochs'],self.len_loader)

        self.scheduler  = CosineAnnealingWarmupRestarts(optimizer         = self.optimizer,
                                                        first_cycle_steps = config['scheduler']['first_cycle_steps'],
                                                        cycle_mult        = config['scheduler']['cycle_mult'],
                                                        max_lr            = config['scheduler']['max_lr'],
                                                        min_lr            = config['scheduler']['min_lr'],
                                                        warmup_steps      = config['scheduler']['warmup_steps'],
                                                        gamma             = config['scheduler']['gamma'])
        # self.scheduler  = torch.optim.lr_scheduler.CosineAnnealingLR()
    def train(self):
        for e in range(self.config['num_epochs']):
            idx = 0
            for src,target_input, target_output, target_padding in self.dataloader:
                start_time     = time.perf_counter()
                logits         = self.model(src,target_input,target_padding) # (B,L,V)
                target_padding = target_padding.reshape(-1)
                target_output  = target_output.reshape(-1)
                logits         = logits[target_padding!=0]
                target_output  = target_output[target_padding!=0]
                loss           = self.criterion(logits,target_output)
                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(),max_norm=self.config["max_grad_norm"])
                self.optimizer.step()
                self.scheduler.step()
                with torch.no_grad():
                    acc = torch.mean((torch.argmax(logits,dim=1)==target_output).float())
                    idx+=1
                    self.stat.update_loss(loss.detach().item())
                    self.stat.update_acc(acc,torch.sum(target_padding).item())
                    self.pro_bar.step(idx,e,self.stat.loss,self.stat.acc,start_time)
            
            self.stat.reset()
                


