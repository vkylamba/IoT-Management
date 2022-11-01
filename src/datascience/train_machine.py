from sklearn import linear_model
from sklearn.neural_network import MLPClassifier
import os
import csv
import pickle


class Train(object):
    """
        Class to train the models based on data.
    """

    def __init__(self):
        self.read_models()

    def read_models(self):
        self.targets = {}
        self.dir_path = os.path.dirname(os.path.abspath(__file__))

        files_list = os.listdir(self.dir_path)
        for file_name in files_list:
            if file_name.endswith('.coef'):
                self.targets[file_name.strip('.coef')] = pickle.load(open(os.path.join(self.dir_path, file_name), 'rb'))

    def read_csv(self, filename):
        X = []
        Y = []
        self.filename = filename

        with open(self.filename) as csvfile:
            spamreader = csv.reader(csvfile, delimiter=',')
            header = None
            for row in spamreader:
                if header is None:
                    header = row
                    self.x_header = header[0:8]
                    self.y_header = header[8:]
                    print("X={}".format(header[0:8]))
                    print("Y={}".format(header[8:]))
                    continue
                x = [float(val) for val in row[0:8]]
                y = [int(val) for val in row[8:]]
                X.append(x)
                Y.append(y)
        return X, Y

    def train(self):
        self.model_list = []
        X = []
        Y = []
        for filename in os.listdir(os.path.join(self.dir_path, 'data')):
            if filename.endswith('.csv'):
                file_path = os.path.join(os.path.join(self.dir_path, 'data'), filename)
                print(f"Data file is: {file_path}")
                x, y = self.read_csv(file_path)
                X += x
                Y += y

        for i in range(0, len(Y[0])):
            ys = []
            for y in Y:
                ys.append(y[i])
            self.reg = linear_model.LinearRegression()
            # self.reg = MLPClassifier(solver='lbfgs', alpha=1e-5, hidden_layer_sizes=(5, 4, 3, 2), random_state=1)
            self.reg.fit(X, ys)
            self.model_list.append(self.reg)
            pickle.dump(self.reg, open(self.dir_path + "/{}.coef".format(self.y_header[i]), 'wb'))


if __name__ == '__main__':

    model = Train()
    model.train()

    # X, Y = model.read_csv('data/data_2017_05_19_12.csv')
    # model.targets['CFL'].predict([X[0]])
