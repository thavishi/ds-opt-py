import os
import argparse
import time
import numpy as np
from   numpy import zeros, newaxis
import scipy.io as sio

import torch
import torch.nn as nn
import torch.optim as optim

# To compare with my DS learning approach
from ds_tools.nonlinear_ds import *

def load_trajectories(file_name):
    '''reads trajectory data from a text file'''
    with open(file_name, 'r') as f:
        line = f.readline()
        l = []
        t = []
        header = []
        x = []
        y = []        
        while line:
            if line.startswith('#'):
                header.append(line)
            else:
                data = line.split(' ')
                l.append(int(data[0]))
                t.append(float(data[1]))
                x.append(float(data[2]))
                y.append(float(data[3]))                            
            line = f.readline()
    return l,t,x,y


parser = argparse.ArgumentParser('ODE demo')
parser.add_argument('--method', type=str, choices=['dopri5', 'adams'], default='dopri5')
parser.add_argument('--data_size', type=int, default=1000)    
parser.add_argument('--batch_time', type=int, default=10)
parser.add_argument('--batch_size', type=int, default=10)
parser.add_argument('--niters', type=int, default=5000)
parser.add_argument('--test_freq', type=int, default=20)
parser.add_argument('--viz', action='store_true')
parser.add_argument('--gpu', type=int, default=1)
parser.add_argument('--adjoint', action='store_true')
args = parser.parse_args()

device = torch.device('cuda:' + str(args.gpu) if torch.cuda.is_available() else 'cpu')

demo_type = 0
if demo_type == 1:
    ####################################################
    ########## This is for the original demo ###########
    ####################################################
    if args.adjoint:
        from torchdiffeq import odeint_adjoint as odeint
    else:
        from torchdiffeq import odeint        

    # Generating the "ground-truth data" for the spiral example
    true_y0 = torch.tensor([[2., 0.]])
    # true_y0 = torch.tensor([[1., 0.]])
    t = torch.linspace(0., 25., args.data_size)
    true_A = torch.tensor([[-0.1, 2.0], [-2.0, -0.1]])
    # true_A = torch.tensor([[-0.1, 2.0], [0.0, -0.1]])
    class Lambda(nn.Module):

        def forward(self, t, y):
            return torch.mm(y**3, true_A)

    with torch.no_grad():
        true_y = odeint(Lambda(), true_y0, t, method='dopri5')
        print(true_y.shape)    
    args.data_size = 1000

else:
    ################################################################
    ########## Use data from drawn trajectories with GUI ###########
    ################################################################
    if args.adjoint:
        from torchdiffeq import odeint_adjoint as odeint
    else:
        from torchdiffeq import odeint   

    raw = 0
    if raw == 1:
        ############      From RAW Data     ############
        # Load trajectories from file and plot
        file_name = './data/human_demonstrated_trajectories.dat'
        file_name = './data/human_demonstrated_trajectories_Mar22_22:33:43.dat'
        l_,t_,x_,y_   = load_trajectories(file_name)
        
        # Extract the first trajectory
        l_0            = np.equal(np.array(l_), np.array([0]*len(l_)))
        t_np           = abs(np.array(t_))
        t_masked       = t_np[l_0]
        true_y_np      = np.array([x_,y_]).transpose()
        true_y_masked  = true_y_np[l_0,:]
        true_y_masked  = true_y_masked[1:,:]
        dim, data_size = true_y_masked.shape    
        true_y_tensor  = true_y_masked[:,newaxis,:]

        # Convert to torch!    
        args.data_size  = 415
        args.batch_size = 20
        t               = torch.from_numpy(t_masked[1:]).float().to(device)
        true_y0         = torch.tensor([[x_[0], y_[0]]])    
        true_y          = torch.from_numpy(true_y_tensor).float().to(device)
    else: 
        ############      From Integrated DS     ############
        #### Load learned DS for Semi spiral shape ####
        models_dir = './models/'
        model_name = 'test2.yml'
        
        # Load learned DS
        lpv_ds     = lpv_DS(filename=models_dir+model_name,order_type='F')    
        ds_fun     = lambda x: lpv_ds.get_ds(x)         

        class LambdaDS(nn.Module):

            def forward(self, t, y):
                y_dot_np    = ds_fun(y.numpy().transpose())
                y_dot_torch = torch.tensor([[y_dot_np[0], y_dot_np[1]]])    
                return y_dot_torch

        dt         = lpv_ds.get_dt()
        x0_all     = lpv_ds.get_x0all()
        true_y0    = torch.tensor([[x0_all[0,0], x0_all[1,0]]])

        # integrate learned DS
        t          = torch.linspace(0., dt/2*args.data_size, args.data_size)
        true_y     = odeint(LambdaDS(), true_y0, t, method='dopri5')
        # true_y     = odeint(LambdaDS(), true_y0, t, method='euler')

def get_batch():
    some_value = np.arange(args.data_size - args.batch_time, dtype=np.int64)
    s = torch.from_numpy(np.random.choice(some_value, args.batch_size, replace=False))
    batch_y0 = true_y[s]  # (M, D)
    batch_t = t[:args.batch_time]  # (T)
    batch_y = torch.stack([true_y[s + i] for i in range(args.batch_time)], dim=0)  # (T, M, D)
    return batch_y0, batch_t, batch_y


def makedirs(dirname):
    if not os.path.exists(dirname):
        os.makedirs(dirname)


if args.viz:
    # makedirs('png')
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(12, 4), facecolor='white')
    ax_traj = fig.add_subplot(131, frameon=False)
    ax_phase = fig.add_subplot(132, frameon=False)
    ax_vecfield = fig.add_subplot(133, frameon=False)
    plt.show(block=False)


def visualize(true_y, pred_y, odefunc, itr):

    if args.viz:

        ax_traj.cla()
        ax_traj.set_title('Trajectories')
        ax_traj.set_xlabel('t')
        ax_traj.set_ylabel('x,y')
        ax_traj.plot(t.numpy(), true_y.numpy()[:, 0, 0], t.numpy(), true_y.numpy()[:, 0, 1], 'g-')
        ax_traj.plot(t.numpy(), pred_y.numpy()[:, 0, 0], '--', t.numpy(), pred_y.numpy()[:, 0, 1], 'b--')
        ax_traj.set_xlim(t.min(), t.max())
        ax_traj.set_ylim(-2, 2)
        ax_traj.legend()

        ax_phase.cla()
        ax_phase.set_title('Phase Portrait')
        ax_phase.set_xlabel('x')
        ax_phase.set_ylabel('y')
        ax_phase.plot(true_y.numpy()[:, 0, 0], true_y.numpy()[:, 0, 1], 'g-')
        ax_phase.plot(pred_y.numpy()[:, 0, 0], pred_y.numpy()[:, 0, 1], 'b--')
        if demo_type == 1:
            ax_phase.set_xlim(-2, 2)
            ax_phase.set_ylim(-2, 2)
        else:
            ax_phase.set_xlim(-0.25, 1.25)
            ax_phase.set_ylim(0, 1)

        ax_vecfield.cla()
        ax_vecfield.set_title('Learned Vector Field')
        ax_vecfield.set_xlabel('x')
        ax_vecfield.set_ylabel('y')

        y, x = np.mgrid[-2:2:21j, -2:2:21j]
        dydt = odefunc(0, torch.Tensor(np.stack([x, y], -1).reshape(21 * 21, 2))).cpu().detach().numpy()
        mag = np.sqrt(dydt[:, 0]**2 + dydt[:, 1]**2).reshape(-1, 1)
        dydt = (dydt / mag)
        dydt = dydt.reshape(21, 21, 2)        
        u = dydt[:, :, 0]
        v = dydt[:, :, 1]
        ax_vecfield.streamplot(x, y, u, v, color="black")
        if demo_type == 1:
            ax_vecfield.set_xlim(-2, 2)
            ax_vecfield.set_ylim(-2, 2)
        else:
            ax_vecfield.set_xlim(-0.25, 1.25)
            ax_vecfield.set_ylim(0, 1)

        fig.tight_layout()
        # plt.savefig('png/{:03d}'.format(itr))
        plt.draw()
        plt.pause(0.001)


class ODEFunc(nn.Module):

    def __init__(self):
        super(ODEFunc, self).__init__()

        self.net = nn.Sequential(
            nn.Linear(2, 50),
            nn.Tanh(),
            nn.Linear(50, 2),
        )

        for m in self.net.modules():
            if isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, mean=0, std=0.1)
                nn.init.constant_(m.bias, val=0)

    def forward(self, t, y):
        return self.net(y**3)


class RunningAverageMeter(object):
    """Computes and stores the average and current value"""

    def __init__(self, momentum=0.99):
        self.momentum = momentum
        self.reset()

    def reset(self):
        self.val = None
        self.avg = 0

    def update(self, val):
        if self.val is None:
            self.avg = val
        else:
            self.avg = self.avg * self.momentum + val * (1 - self.momentum)
        self.val = val


if __name__ == '__main__':

    ii = 0

    func = ODEFunc()
    optimizer = optim.RMSprop(func.parameters(), lr=1e-3)
    end = time.time()

    time_meter = RunningAverageMeter(0.97)
    loss_meter = RunningAverageMeter(0.97)

    for itr in range(1, args.niters + 1):
        optimizer.zero_grad()
        batch_y0, batch_t, batch_y = get_batch()
        pred_y = odeint(func, batch_y0, batch_t)
        loss = torch.mean(torch.abs(pred_y - batch_y))
        loss.backward()
        optimizer.step()

        time_meter.update(time.time() - end)
        loss_meter.update(loss.item())

        if itr % args.test_freq == 0:
            with torch.no_grad():
                pred_y = odeint(func, true_y0, t)
                loss = torch.mean(torch.abs(pred_y - true_y))
                print('Iter {:04d} | Total Loss {:.6f}'.format(itr, loss.item()))
                visualize(true_y, pred_y, func, ii)
                ii += 1

        end = time.time()
