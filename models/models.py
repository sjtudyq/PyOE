import logging
from abc import abstractmethod
from typing import Literal
from pytorch_tabnet.tab_model import TabNetClassifier, TabNetRegressor
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from OEBench.model import *
from OEBench.ewc import *
from OEBench.arf import *
from OEBench.armnet import *
from ..algorithms.loss import *
from ..dataloaders import Dataloader


class ModelTemplate:
    """
    A template class for all models. It contains the common attributes and methods for all models.
    ATTENTION: If you need to use your own model, you should inherit this class and assign self.net in
    the __init__ method. The self.net should be a PyTorch model.
    """

    def __init__(
        self,
        dataloader: Dataloader,
        ensemble: int = 1,
        device: Literal["cpu", "cuda"] = "cuda",
    ):
        # fetch metadata of the dataset from dataloader
        self.column_count = dataloader.get_num_columns()
        self.output_dim = dataloader.get_output_dim()
        self.window_size = dataloader.get_window_size()
        self.task = dataloader.get_task()
        self.device = device
        # some default values
        self.net_ensemble = None
        self.ensemble_num = ensemble

    @abstractmethod
    def process_model(self, **kwargs):
        """
        This function is used to process the model before training.
        You should assign some values for later use in training
        such as optimizer, criterion, etc. Attention: this function
        is called in the trainer class.
        """
        pass

    def get_net(self):
        return self.net

    def get_net_ensemble(self):
        return self.net_ensemble

    def get_model_type(self) -> str:
        return self.model_type

    def get_ensemble_number(self) -> int:
        return self.ensemble_num

    def get_device(self) -> Literal["cpu", "cuda"]:
        return self.device


class MlpModel(ModelTemplate):
    """
    A simple MLP model for classification and regression tasks.
    """

    def __init__(
        self,
        dataloader: Dataloader,
        ensemble: int = 1,
        device: Literal["cpu", "cuda"] = "cuda",
    ):
        super().__init__(dataloader, ensemble, device)
        self.model_type = "mlp"
        # initialization for MLP model
        hidden_layers = [32, 16, 8]
        self.net = FcNet(self.column_count, hidden_layers, self.output_dim).to(device)
        self.net_ensemble = [
            FcNet(self.column_count, hidden_layers, self.output_dim)
            for i in range(ensemble)
        ]

    def process_model(self, lr: float, **kwargs):
        # choose optimizer for tree models
        self.optimizer = torch.optim.SGD(
            filter(lambda p: p.requires_grad, self.net.parameters()),
            lr=lr,
        )

        # choose criterion for different tasks
        if self.task == "classification":
            self.criterion = nn.CrossEntropyLoss().to(self.device)
            self.loss = classification_loss(self.net)
        elif self.task == "regression":
            self.criterion = nn.MSELoss().to(self.device)
            self.loss = regression_loss(self.net)
        else:
            logging.error(f"Task not supported: {self.task}")
            raise ValueError("Task not supported.")

    def train_naive(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        In this function, we will train the model using the input data.
        """
        X, y, y_outlier, batch_size, epochs = self.__train_naive_header(
            X, y, y_outlier, batch_size, epochs, need_test
        )
        self.__train_naive_body(X, y, y_outlier, batch_size, epochs, need_test)
        self.__train_naive_footer(X, y, y_outlier, batch_size, epochs, need_test)

    def __train_naive_header(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is used to preprocess the input data.
        """
        # if the task is classification, we should convert the data type of y to long
        if self.task == "classification":
            y = y.long()

        # test preparation
        if need_test:
            accuracy_loss = self.loss.loss(X, y, y_outlier)
            logging.info(f"Current accuracy loss: {accuracy_loss}")

        return (X, y, y_outlier, batch_size, epochs)

    def __train_naive_body(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is the main part of training.
        """
        # training for mlp and armnet with epochs times
        for epoch in range(epochs):
            # logging some information for each epoch
            logging.info(f"Starting epoch {epoch + 1}/{epochs}")
            for batch_ind in range(0, y.shape[0], batch_size):
                # get a batch of x and y
                batch_x = torch.tensor(
                    X[batch_ind : batch_ind + batch_size], dtype=torch.float
                ).to(self.device)
                batch_y = torch.tensor(
                    y[batch_ind : batch_ind + batch_size], dtype=torch.float
                ).to(self.device)

                # using gradient descent to optimize the parameters
                self.optimizer.zero_grad()
                # the loss function require 0D or 1D tensors for input
                out: torch.Tensor = self.net(batch_x).reshape(-1)
                ref: torch.Tensor = batch_y.reshape(-1)
                loss = self.criterion(out, ref)
                loss.backward()
                self.optimizer.step()

    def __train_naive_footer(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is used to postprocess the model after training.
        """
        pass

    def train_icarl(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        buffer_size: int,
        need_test: bool = False,
    ):
        """
        This function iCaRL implements the training process for MLP model.
        """
        X, y, y_outlier, batch_size, epochs, buffer_size = self.__train_icarl_header(
            X, y, y_outlier, batch_size, epochs, buffer_size, need_test
        )
        self.__train_icarl_body(
            X, y, y_outlier, batch_size, epochs, buffer_size, need_test
        )
        self.__train_icarl_footer(
            X, y, y_outlier, batch_size, epochs, buffer_size, need_test
        )

    def __train_icarl_header(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        buffer_size: int,
        need_test: bool = False,
    ):
        self.x_example = None
        self.y_example = None
        # TODO: need_test is not used in this function

        return (X, y, y_outlier, batch_size, epochs, buffer_size)

    def __train_icarl_body(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        buffer_size: int,
        need_test: bool = False,
    ):
        # train epochs times
        for epoch in range(epochs):
            logging.info(f"Starting epoch {epoch + 1}/{epochs}")
            # train the model with batch_size each time
            for batch_ind in range(0, y.shape[0], batch_size):
                batch_x = X[batch_ind : batch_ind + batch_size].to(self.device)
                batch_y = y[batch_ind : batch_ind + batch_size].to(self.device)
                # zero the gradient
                self.optimizer.zero_grad()
                out = self.net(batch_x)
                if self.task == "regression":
                    out = out.reshape(-1)
                # calculate the loss
                loss = self.criterion(out, batch_y)
                if self.x_example is not None:
                    out_e = self.net(self.x_example)
                    loss += self.criterion(out_e, self.y_example)
                # backward and optimize
                loss.backward()
                self.optimizer.step()

    def __train_icarl_footer(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        buffer_size: int,
        need_test: bool = False,
    ):
        # prepare some variables here
        examples = [[] for _ in range(self.output_dim)]
        buffer_class = int(buffer_size / self.output_dim)

        # post processing
        if self.task == "regression":
            if self.x_example is None:
                features = self.net.feature_extractor(X).detach()
                avg = torch.mean(features, dim=0).unsqueeze(0)
                distance = torch.norm(features - avg, dim=1)
                _, indices = torch.topk(distance, k=buffer_size, largest=False)
                self.x_example = X[indices].to(self.device)
                self.y_example = y[indices].to(self.device)
        elif self.task == "classification":
            update = False
            # iterate over all output dimensions
            for i in range(self.output_dim):
                if len(examples[i]) < buffer_class and i in y:
                    # get some information of the current class
                    data_class = X[y == i]
                    features = self.net.feature_extractor(data_class).detach()
                    avg = torch.mean(features, dim=0).unsqueeze(0)
                    distance = torch.norm(features - avg, dim=1)
                    _, indices = torch.topk(
                        distance,
                        k=min(buffer_class - len(examples[i]), len(distance)),
                        largest=False,
                    )
                    self.examples[i] = (
                        data_class[indices]
                        if len(examples[i]) == 0
                        else torch.cat((examples[i], data_class[indices]), dim=0)
                    )
                    update = True

            # if update is needed
            if update:
                self.x_example = []
                for i in range(self.output_dim):
                    if len(examples[i]) == 0:
                        continue
                    if len(self.x_example) == 0:
                        self.x_example = examples[i]
                        self.y_example = torch.ones(examples[i].shape[0]) * i
                    else:
                        self.x_example = torch.cat((self.x_example, examples[i]), dim=0)
                        self.y_example = torch.cat(
                            (self.y_example, torch.ones(examples[i].shape[0]) * i),
                            dim=0,
                        )

                # convert the data type of y to long and move the data to device
                self.x_example = self.x_example.to(self.device)
                self.y_example = self.y_example.long().to(self.device)


class TreeModel(ModelTemplate):
    """
    A simple Tree model for classification and regression tasks.
    """

    def __init__(
        self,
        dataloader: Dataloader,
        ensemble: int = 1,
        device: Literal["cpu"] = "cpu",
    ):
        super().__init__(dataloader, ensemble, device)
        self.model_type = "tree"
        # initialization for Tree model
        if self.task == "classification":
            self.net = DecisionTreeClassifier()
            self.net_ensemble = [DecisionTreeClassifier() for i in range(ensemble)]
        elif self.task == "regression":
            self.net = DecisionTreeRegressor()
            self.net_ensemble = [DecisionTreeRegressor() for i in range(ensemble)]
        else:
            logging.error(f"Task {self.task} not supported.")
            raise ValueError("Task not supported.")

    def process_model(self, **kwargs):
        # choose criterion for different tasks
        if self.task == "classification":
            self.criterion = nn.CrossEntropyLoss().to(self.device)
            self.loss = classification_loss_tree(self.net)
        elif self.task == "regression":
            self.criterion = nn.MSELoss().to(self.device)
            self.loss = regression_loss_tree(self.net)
        else:
            logging.error(f"Task not supported: {self.task}")
            raise ValueError("Task not supported.")

    def train_naive(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        In this function, we will train the model using the input data.
        """
        X, y, y_outlier, batch_size, epochs = self.__train_naive_header(
            X, y, y_outlier, batch_size, epochs, need_test
        )
        self.__train_naive_body(X, y, y_outlier, batch_size, epochs, need_test)
        self.__train_naive_footer(X, y, y_outlier, batch_size, epochs, need_test)

    def __train_naive_header(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is used to preprocess the input data.
        """
        # if the task is classification, we should convert the data type of y to long
        if self.task == "classification":
            y = y.long()

        # test preparation
        if need_test:
            accuracy_loss = self.loss.loss(X, y, y_outlier)
            logging.info(f"Current accuracy loss: {accuracy_loss}")

        return (X, y, y_outlier, batch_size, epochs)

    def __train_naive_body(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is the main part of training.
        """
        # training for mlp and armnet with epochs times
        self.net.fit(X, y)

    def __train_naive_footer(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is used to postprocess the model after training.
        """
        pass

    def train_icarl(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        buffer_size: int,
        need_test: bool = False,
    ):
        """
        iCaRL training process only supports neural network models.
        """
        logging.error(f"Model not supported: {self.model_type}")
        raise ValueError("ICaRL only supports NN model.")


class GbdtModel(ModelTemplate):
    """
    A simple GBDT model for classification and regression tasks.
    """

    def __init__(
        self,
        dataloader: Dataloader,
        ensemble: int = 1,
        device: Literal["cpu"] = "cpu",
    ):
        super().__init__(dataloader, ensemble, device)
        self.model_type = "gbdt"
        # initialization for GBDT model
        if self.task == "classification":
            self.net = GradientBoostingClassifier()
            self.net_ensemble = [GradientBoostingClassifier() for i in range(ensemble)]
        elif self.task == "regression":
            self.net = GradientBoostingRegressor()
            self.net_ensemble = [GradientBoostingRegressor() for i in range(ensemble)]
        else:
            logging.error(f"Task {self.task} not supported.")
            raise ValueError("Task not supported.")

    def process_model(self, **kwargs):
        # choose criterion for different tasks
        if self.task == "classification":
            self.criterion = nn.CrossEntropyLoss().to(self.device)
            self.loss = classification_loss_tree(self.net)
        elif self.task == "regression":
            self.criterion = nn.MSELoss().to(self.device)
            self.loss = regression_loss_tree(self.net)
        else:
            logging.error(f"Task not supported: {self.task}")
            raise ValueError("Task not supported.")

    def train_naive(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        In this function, we will train the model using the input data.
        """
        X, y, y_outlier, batch_size, epochs = self.__train_naive_header(
            X, y, y_outlier, batch_size, epochs, need_test
        )
        self.__train_naive_body(X, y, y_outlier, batch_size, epochs, need_test)
        self.__train_naive_footer(X, y, y_outlier, batch_size, epochs, need_test)

    def __train_naive_header(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is used to preprocess the input data.
        """
        # if the task is classification, we should convert the data type of y to long
        if self.task == "classification":
            y = y.long()

        # test preparation
        if need_test:
            accuracy_loss = self.loss.loss(X, y, y_outlier)
            logging.info(f"Current accuracy loss: {accuracy_loss}")

        return (X, y, y_outlier, batch_size, epochs)

    def __train_naive_body(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is the main part of training.
        """
        # training for mlp and armnet with epochs times
        self.net.fit(X, y)

    def __train_naive_footer(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is used to postprocess the model after training.
        """
        pass

    def train_icarl(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        buffer_size: int,
        need_test: bool = False,
    ):
        """
        iCaRL training process only supports neural network models.
        """
        logging.error(f"Model not supported: {self.model_type}")
        raise ValueError("ICaRL only supports NN model.")


class TabnetModel(ModelTemplate):
    """
    A simple TabNet model for classification and regression tasks.
    """

    def __init__(
        self,
        dataloader: Dataloader,
        ensemble: int = 1,
        device: Literal["cpu"] = "cpu",
    ):
        super().__init__(dataloader, ensemble, device)
        self.model_type = "tabnet"
        # initialization for TabNet model
        if self.task == "classification":
            self.net = TabNetClassifier(seed=0)
        elif self.task == "regression":
            self.net = TabNetRegressor(seed=0)
        else:
            logging.error(f"Task {self.task} not supported.")
            raise ValueError("Task not supported.")

    def process_model(self, **kwargs):
        # choose criterion for different tasks
        if self.task == "classification":
            self.criterion = nn.CrossEntropyLoss().to(self.device)
            self.loss = classification_loss_tree(self.net)
        elif self.task == "regression":
            self.criterion = nn.MSELoss().to(self.device)
            self.loss = regression_loss_tree(self.net)
        else:
            logging.error(f"Task not supported: {self.task}")
            raise ValueError("Task not supported.")

    def train_naive(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        In this function, we will train the model using the input data.
        """
        X, y, y_outlier, batch_size, epochs = self.__train_naive_header(
            X, y, y_outlier, batch_size, epochs, need_test
        )
        self.__train_naive_body(X, y, y_outlier, batch_size, epochs, need_test)
        self.__train_naive_footer(X, y, y_outlier, batch_size, epochs, need_test)

    def __train_naive_header(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is used to preprocess the input data.
        """
        # preprocess the input data according to the task
        if self.task == "regression":
            y = y.reshape(-1, 1)
        # if the task is classification, we should convert the data type of y to long
        elif self.task == "classification":
            y = y.long()

        # test preparation
        if need_test:
            accuracy_loss = self.loss.loss(X, y, y_outlier)
            logging.info(f"Current accuracy loss: {accuracy_loss}")

        # transit the data type of X and y to numpy array
        X: np.ndarray = X.numpy()
        y: np.ndarray = y.numpy()

        return (X, y, y_outlier, batch_size, epochs)

    def __train_naive_body(
        self,
        X: np.ndarray,
        y: np.ndarray,
        y_outlier: np.ndarray,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is the main part of training.
        """
        self.net.fit(
            X,
            y,
            batch_size=batch_size,
            virtual_batch_size=batch_size,
            max_epochs=epochs,
        )

    def __train_naive_footer(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is used to postprocess the model after training.
        """
        pass

    def train_icarl(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        buffer_size: int,
        need_test: bool = False,
    ):
        """
        iCaRL training process only supports neural network models.
        """
        logging.error(f"Model not supported: {self.model_type}")
        raise ValueError("ICaRL only supports NN model.")


class ArmnetModel(ModelTemplate):
    """
    A simple ARMNet model for classification and regression tasks.
    """

    def __init__(
        self,
        dataloader: Dataloader,
        ensemble: int = 1,
        device: Literal["cpu", "cuda"] = "cuda",
    ):
        super().__init__(dataloader, ensemble, device)
        self.model_type = "armnet"
        # initialization for ARMNet model
        self.net = ARMNetModel(
            self.column_count,
            self.column_count,
            self.column_count,
            2,
            1.7,
            32,
            3,
            16,
            0,
            False,
            3,
            16,
            noutput=self.output_dim,
        ).to(device)

    def process_model(self, lr: float, **kwargs):
        # choose optimizer for tree models
        self.optimizer = torch.optim.SGD(
            filter(lambda p: p.requires_grad, self.net.parameters()),
            lr=lr,
        )

        # choose criterion for different tasks
        if self.task == "classification":
            self.criterion = nn.CrossEntropyLoss().to(self.device)
            self.loss = classification_loss(self.net)
        elif self.task == "regression":
            self.criterion = nn.MSELoss().to(self.device)
            self.loss = regression_loss(self.net)
        else:
            logging.error(f"Task not supported: {self.task}")
            raise ValueError("Task not supported.")

    def __preprocess_x(self, X: torch.Tensor) -> dict:
        return {
            "value": X,
            "id": torch.arange(X.shape[1])
            .repeat(X.shape[0])
            .view(X.shape[0], -1)
            .to(self.device),
        }

    def train_naive(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        In this function, we will train the model using the input data.
        """
        X, y, y_outlier, batch_size, epochs = self.__train_naive_header(
            X, y, y_outlier, batch_size, epochs, need_test
        )
        self.__train_naive_body(X, y, y_outlier, batch_size, epochs, need_test)
        self.__train_naive_footer(X, y, y_outlier, batch_size, epochs, need_test)

    def __train_naive_header(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is used to preprocess the input data.
        """
        # if the task is classification, we should convert the data type of y to long
        if self.task == "classification":
            y = y.long()

        # test preparation
        if need_test:
            accuracy_loss = self.loss.loss(self.__preprocess_x(X), y, y_outlier)
            logging.info(f"Current accuracy loss: {accuracy_loss}")

        return (X, y, y_outlier, batch_size, epochs)

    def __train_naive_body(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is the main part of training.
        """
        # training for mlp and armnet with epochs times
        for epoch in range(epochs):
            # logging some information for each epoch
            logging.info(f"Starting epoch {epoch + 1}/{epochs}")
            for batch_ind in range(0, y.shape[0], batch_size):
                # get a batch of x and y
                batch_y = torch.tensor(
                    y[batch_ind : batch_ind + batch_size], dtype=torch.float
                ).to(self.device)
                batch_x = self.__preprocess_x(
                    torch.tensor(
                        X[batch_ind : batch_ind + batch_size], dtype=torch.float
                    )
                )

                # using gradient descent to optimize the parameters
                self.optimizer.zero_grad()
                # the loss function require 0D or 1D tensors for input
                out: torch.Tensor = self.net(batch_x).reshape(-1)
                ref: torch.Tensor = batch_y.reshape(-1)
                loss = self.criterion(out, ref)
                loss.backward()
                self.optimizer.step()

    def __train_naive_footer(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        need_test: bool = False,
    ):
        """
        This function is used to postprocess the model after training.
        """
        pass

    def train_icarl(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        y_outlier: torch.Tensor,
        batch_size: int,
        epochs: int,
        buffer_size: int,
        need_test: bool = False,
    ):
        """
        iCaRL training process only supports neural network models.
        """
        logging.error(f"Model not supported: {self.model_type}")
        raise ValueError("ICaRL only supports NN model.")
