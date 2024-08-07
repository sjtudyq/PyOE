import torch
from torch import nn
from typing import Optional
from abc import abstractmethod


class LossTemplate:
    """
    This is a template for loss function. We implemented some common loss
    functions and you can also implement your own loss function using this template.
    """

    def __init__(self, net: nn.Module, **kargws) -> None:
        self.net = net

    @abstractmethod
    def loss(
        self,
        x_window: torch.Tensor,
        y_window: torch.Tensor,
        y_outlier: Optional[torch.Tensor] = None,
        **kargws,
    ) -> torch.Tensor:
        """
        This is the loss function. You can implement your own loss function here.
        """
        pass


class classification_loss(LossTemplate):

    def __init__(self, net: nn.Module, **kwargs):
        super().__init__(net, **kwargs)

    def loss(
        self,
        x_window: torch.Tensor,
        y_window: torch.Tensor,
        y_outlier: Optional[torch.Tensor] = None,
        **kwargs,
    ):
        # calculate the predicted label
        out: torch.Tensor = self.net(x_window)
        _, pred_label = torch.max(out.data.view(y_window.shape[0], -1), 1)

        # calculate the accuracy
        if y_outlier is None:
            acc = (pred_label == y_window).sum().item() / y_window.shape[0]
        else:
            acc = (
                (pred_label == y_window)
                * (1 - y_outlier).sum().item()
                / (y_window.shape[0] - y_outlier.sum().item())
            )

        return 1 - acc


class classification_loss_tree(LossTemplate):

    def __init__(self, net: nn.Module, **kwargs):
        super().__init__(net, **kwargs)

    def loss(
        self,
        x_window: torch.Tensor,
        y_window: torch.Tensor,
        y_outlier: Optional[torch.Tensor] = None,
        **kwargs,
    ):
        # calculate the predicted label
        pred_label = torch.LongTensor(self.net.predict(x_window))

        # calculate the accuracy
        if y_outlier is None:
            acc = (pred_label == y_window).sum().item() / y_window.shape[0]
        else:
            acc = (
                (pred_label == y_window)
                * (1 - y_outlier).sum().item()
                / (y_window.shape[0] - y_outlier.sum().item())
            )

        return 1 - acc


class regression_loss(LossTemplate):

    def __init__(self, net: nn.Module, **kwargs):
        super().__init__(net, **kwargs)

    def loss(
        self,
        x_window: torch.Tensor,
        y_window: torch.Tensor,
        y_outlier: Optional[torch.Tensor] = None,
        **kwargs,
    ):
        # calculate the predicted label
        out = self.net(x_window).reshape(-1).detach()

        # calculate the loss
        if y_outlier is None:
            loss = torch.mean(torch.square(out - y_window))
        else:
            loss = torch.sum(torch.square(out - y_window) * (1 - y_outlier)) / (
                y_window.shape[0] - y_outlier.sum().item()
            )
        return loss.item()


class regression_loss_tree(LossTemplate):

    def __init__(self, net: nn.Module, **kwargs):
        super().__init__(net, **kwargs)

    def loss(
        self,
        x_window: torch.Tensor,
        y_window: torch.Tensor,
        y_outlier: Optional[torch.Tensor] = None,
        **kwargs,
    ):
        # calculate the predicted label
        out = torch.Tensor(self.net.predict(x_window))

        # calculate the loss
        if y_outlier is None:
            loss = torch.mean(torch.square(out - y_window))
        else:
            loss = torch.sum(torch.square(out - y_window) * (1 - y_outlier)) / (
                y_window.shape[0] - y_outlier.sum().item()
            )
        return loss.item()
