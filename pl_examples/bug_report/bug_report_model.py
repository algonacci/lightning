import os
import torch
from torch.utils.data import Dataset, DataLoader
import pytorch_lightning as pl
from pytorch_lightning import LightningModule, Trainer
from pytorch_lightning.callbacks import ModelCheckpoint
from pytorch_lightning.plugins import DeepSpeedPlugin
from transformers.optimization import get_scheduler

class RandomDataset(Dataset):

    def __init__(self, size, length):
        self.len = length
        self.data = torch.randn(length, size)

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return self.len


class BoringModel(LightningModule):

    def __init__(self):
        super().__init__()
        self.layer = torch.nn.Linear(32, 2)

    def forward(self, x):
        return self.layer(x)

    def train_dataloader(self):
        return DataLoader(RandomDataset(32, 64), batch_size=2)

    def training_step(self, batch, batch_idx):
        loss = self(batch).sum()
        self.log("train_loss", loss)
        return loss

    def validation_step(self, batch, batch_idx):
        loss = self(batch).sum()
        self.log("valid_loss", loss)
        return loss

    def test_step(self, batch, batch_idx):
        loss = self(batch).sum()
        self.log("test_loss", loss)
        return loss

    def configure_optimizers(self):
        no_decay = ["bias"]
        params_decay = [
            p for n, p in self.named_parameters() if not any(nd in n for nd in no_decay)
        ]
        params_nodecay = [
            p for n, p in self.named_parameters() if any(nd in n for nd in no_decay)
        ]
        optim_groups = [
            {
                "params": params_decay,
                "weight_decay": 0.01,
            },
            {"params": params_nodecay, "weight_decay": 0.0},
        ]
        optimizer = torch.optim.SGD(optim_groups, lr=0.1)
        scheduler = get_scheduler("linear", optimizer, num_warmup_steps=10, num_training_steps=100)
        return ([optimizer], [{"scheduler": scheduler}])

def run():
    train_data = DataLoader(RandomDataset(32, 64), batch_size=4)
    val_data = DataLoader(RandomDataset(32, 64), batch_size=4)
    test_data = DataLoader(RandomDataset(32, 64), batch_size=4)

    model = BoringModel()
    checkpoint_callback = ModelCheckpoint(
        dirpath='tests4/checkpoints',
        save_last=True,
        every_n_train_steps=5,
    )
    trainer = Trainer(
        default_root_dir=os.getcwd(),
        gpus=2,
        limit_train_batches=1.0,
        limit_val_batches=1,
        num_sanity_val_steps=0,
        precision=16,
        accelerator='deepspeed',
        max_steps=50,
        log_every_n_steps=10,
        plugins=[DeepSpeedPlugin(stage=2)],
        weights_summary=None,
        callbacks=[checkpoint_callback, pl.callbacks.LearningRateMonitor(logging_interval="step")],
        #resume_from_checkpoint='tests4/checkpoints/epoch=1-step=49.ckpt',
    )
    trainer.fit(model)
    trainer.test(model, dataloaders=test_data)

    # test lr_scheduler state
    model_state_path = "tests4/checkpoints/epoch=1-step=49.ckpt/global_step50/mp_rank_00_model_states.pt"
    model_state = torch.load(model_state_path, map_location="cpu")
    print(model_state["lr_scheduler"])


if __name__ == '__main__':
    run()