# PyOE

PyOE is a Machine Learning System inspired by [OEBench](https://github.com/Xtra-Computing/OEBench). With this system, you can train models on our datasets with just a few lines of code. For more details, you can visit our [PyOE website](https://pyoe.xtra.science).

## How to Start with PyOE

First, you need to install the dependencies required by PyOE. You can do this by running the following commands:

```shell
pip install numpy
pip install -r requirements.txt
```

We have some examples in the examples folder. You can copy one of these examples to the parent directory of this README file and try running them. If they run successfully, it means the installation is complete.

## Four Main Tasks of PyOE System

Our PyOE system currently supports 4 types of tasks: regression analysis, classification, outlier detection, and concept drift detection. In the following, we will provide examples of code for each of these 4 tasks.

### Regression

To perform *Open Environment* regression analysis using PyOE, follow the steps mentioned earlier: first, load the dataset, then select a model that supports this task, choose a method for handling missing values, and finally, pass all these as parameters to the trainer. By calling the `train` method, the model will be trained automatically.

After that, if you want to make regression predictions, you can get the model using ```model.get_net()```, and then pass the corresponding data to make predictions.

Here is a complete example:

```python
# import the library PyOE
import PyOE

# choose the targeted dataset, model, preprocessor, and trainer
dataloader = PyOE.Dataloader(dataset_name="dataset_experiment_info/beijingPM2.5")
model = PyOE.MlpModel(dataloader=dataloader, device="cuda")
preprocessor = PyOE.Preprocessor(missing_fill="knn2")
trainer = PyOE.NaiveTrainer(dataloader=dataloader, model=model, preprocessor=preprocessor, epochs=16)

# get the trained net
net = model.get_net()
# predict here...
```

### Classification

The classification task is almost identical to the regression task, except that some different loss functions and models are used internally, but this does not affect the usage on the user side. Note that in classification tasks, we use OneHot encoding for the prediction results. Therefore, depending on the number of classes, each prediction result should be a 0-1 vector of the corresponding dimension. Here is a simple example:

```python
# import the library PyOE
import PyOE

# choose the targeted dataset, model, preprocessor, and trainer
dataloader = PyOE.Dataloader(dataset_name="dataset_experiment_info/room_occupancy")
model = PyOE.MlpModel(dataloader=dataloader, device="cuda")
preprocessor = PyOE.Preprocessor(missing_fill="knn2")
trainer = PyOE.NaiveTrainer(dataloader=dataloader, model=model, preprocessor=preprocessor, epochs=1024)

# get the trained net
net = model.get_net()
# predict here...
```

### Outlier Detection

Our PyOE also supports outlier analysis of data. Since outlier detection is solely dependent on the data, we directly call the ```get_outlier``` method of stream models. This method is nearly identical to the outlier detection methods in OEBench, using PyOD's ECOD and IForest models. We consider a point to be an outlier if and only if both of these models agree.

In real-world scenarios, many data are streaming data (e.g., time series data) and need to be updated online. In such cases, streaming algorithms are useful. Therefore, in the streaming models we provide, there is a ```get_model_score``` method that can be used to get the score assigned to data points by the streaming model. By comparing this score with the previous global algorithm or ground truth, you can determine the effectiveness of the streaming algorithm.

Here is an example:

```python
import PyOE
from torch.utils.data import DataLoader as TorchDataLoader

dataloader = PyOE.Dataloader(dataset_name="dataset_experiment_info/beijingPM2.5")
model = PyOE.XStreamDetectorModel(dataloader=dataloader)
# use TorchDataLoader to enumerate X and y
torch_dataloader = TorchDataLoader(dataloader, batch_size=10240)
for X, y, _ in torch_dataloader:
    print(model.get_outlier(X), model.get_outlier_with_stream_model(X))
```

### Concept Drift Detection

Concept drift detection is mainly divided into two scenarios. The first scenario is when the ground truth is unknown. In that case, we use the code below to obtain the detected drift points:

```python
# import the library PyOE
import PyOE

# load data and detect concept drift
dataloader = PyOE.Dataloader(dataset_name="dataset_experiment_info/beijingPM2.5")
print(PyOE.metrics.DriftDelayMetric(dataloader).measure())
```

It will print a list containing all the detected concept drift points. It should be noted that ```PyOE.metrics.DriftDelayMetric``` also contains many parameters that can be used to define the model, sensitivity of detection, and so on.

The second scenario is when the ground truth is known. Use the following code to measure the *Average Concept Drift Delay*:

```python
# import the library PyOE
import PyOE

# load data and detect concept drift
dataloader = PyOE.Dataloader(dataset_name="dataset_experiment_info/beijingPM2.5")
# change the list below with ground truth...
ground_truth_example = [100, 1000, 10000]

print(PyOE.metrics.DriftDelayMetric(dataloader).measure())
```

It will print a floating-point number representing the *Average Concept Drift Delay*.

