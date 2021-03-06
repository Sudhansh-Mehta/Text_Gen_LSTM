# Lab 7 - Text generation with LSTM
#
# Step 1 (not assessed): build and train a model to generate text in the style of a corpus.
#
# Based on the Keras text generation example (https://github.com/fchollet/keras/blob/master/examples/lstm_text_generation.py)
#
# Step 2: build a model to distinguish genuine from fake sentences.
In [ ]:
# Import essential modules
import pickle
import random
import sys
import time

import numpy as np
from sklearn.model_selection import train_test_split

from keras.layers import Input, LSTM, GRU, Dense, Activation
from keras.optimizers import RMSprop
from keras.models import Model, Sequential
from keras.models import save_model
from keras.utils.data_utils import get_file
In [ ]:
# Helper function to sample an index from an array of predictions.
#
# The input array 'preds' should be the output of a text generation model.
# The elements contain the values of the units in the final layer.
# Each unit corresponds to a character in the text alphabet.
# The final layer should have SoftMax activation, and thus the
# value corresponds to the 'strength of prediction' of that character
# as the next output value---so the maximum value indicates which character
# is most strongly predicted (considerd most likely) as the next one.
#
def sample(preds, temperature=0.5):
    # Convert to high-precision datatype (we are going to be manipulating some
    # very small values in this function)
    preds = np.asarray(preds).astype('float64')  
    
    # The next line has the effect of raising each prediction value to the power 1/T.
    # It's done using logs to improve numerical precision.  This is a kind of value-dependent
    # scaling: for T < 1.0 (1/T > 1.0), small values are made smaller (proportionally) than 
    # large values (unlike a linear scaling, such as multiplication by 0.9, which scales all values
    # the same).
    #
    # Example: Consider that we have only two symbols (letters) in our alphabet, and our 
    # probabilities are [0.2, 0.8].  A temperature of 1.0 means 'do not adjust the
    # probabilities at all', so in this case there will be a 20% chance that the 
    # function will return 'symbol 0' and an 80% chance  that it will return 'symbol 1'.
    # Note that symbol 1 is 4x more likely than symbol 0.
    #
    # Now: if we supply a temperature of 0.5, our probabilites will be raised to the
    # power 1/0.5 = 2, becoming [0.04, 0.64].  These will then be normalized to sum to 1,
    # but anyway it is clear that symbol 1 is here 16x (the square of 4x) more likely than 
    # symbol 0.
    #
    # Conversely, for a temperature of 2, our probabilities will be raised to 0.5 (square-rooted),
    # becoming [.4472, 0.8944] - and so here symbol 1 is only 2x (sqrt of 4x) more likely than
    # symbol 0.
    #
    # So: low temperatures make the distribution peakier, exaggerating the difference between
    # values.  High temperatures flatten the distribution, reducing the difference between values.
    #
    # As the return value is a sample of the manipulated distribution, manipulating it to
    # be peakier (by supplying a low temperature) makes the sample more conservative, i.e.
    # more likely to pick the highest-probability symbol.
    #
    # Making the distribution flatter (by suppyling a high temperature) causes the
    # sample to be less conservative, i.e. more likely to pick some lower-likelihood
    # symbol.
    #
    # Phew!
    preds = np.exp(np.log(preds) / temperature)
    
    preds = preds / np.sum(preds)  # ensure that probs sum to 1
    probas = np.random.multinomial(1, preds, 1)  # take 1 sample from the distribution
    return np.argmax(probas)
In [ ]:
# Decide how much data to use for training.
# You might want to reduce this to ~100k for faster experimentation, and then bring it back
# to 600k when you're happy with your network architecture.
# IMPORTANT: mke sure you end up with a 57-symbol alphabet after reducing the corpus size!
# If the number of symbols (shown in the next cell) gets smaller than it was with the full
# corpus, bring your sample size back up.  This is necessary because the encoding used for
# training must match that used for assessment.
desired_num_chars = 600*1000  # Max: 600893

random.seed(43)  # Fix random seed for repeatable results.

# Slurp down all of Nietzsche from Amazon.
path = get_file('nietzsche.txt', origin='https://s3.amazonaws.com/text-datasets/nietzsche.txt')
text = open(path).read().lower()
print('original corpus length:', len(text))

start_index = random.randint(0, len(text) - desired_num_chars - 1)
text = text[start_index:start_index + desired_num_chars]
text
print('length for training:', len(text))
In [ ]:
# Let's have a quick look at a random exceprt.
#
# Caution: Nietzsche might drive you mad: dare you behold more than 1000 of his terrible chars..? 
sample_length = 1000

random.seed(None)  # Seeds random from current time (so re-eval this cell for a new sample).

start_index = random.randint(0, len(text) - sample_length - 1)
print(text[start_index:start_index+sample_length])
In [ ]:
# Establish the alphabet (set of symbols) we are going to use.
chars = sorted(list(set(text)))
print('total chars:', len(chars))
print(chars)

char_indices = dict((c, i) for i, c in enumerate(chars))  # Map to look up index of a particular char (e.g. x['a'] = 0)
indices_char = dict((i, c) for i, c in enumerate(chars))  # Map to look up char at an index (e.g. x[0] = 'a')
In [ ]:
# Establish a training set of semi-redundant (i.e. overlapping) sequences of maxlen characters.
maxlen = 40
step = 3
sentences = []  # Not syntactic sentences, but just sequences of 40 chars pulled from the corpus.
next_chars = [] # next_chars[n] stores the character which followed sentences[n]
for i in range(0, len(text) - maxlen, step):
    sentences.append(text[i: i + maxlen])
    next_chars.append(text[i + maxlen])
print('nb sequences:', len(sentences))
In [ ]:
# Convert the data to one-hot encoding.
# 'x' will contain the one-hot encoding of the training 'sentences'.
# 'y' will contain the one-hot encoding of the 'next char' for each sentence.
#
# 
# Let's consider that we have N sentences of length L:
#
# The 'native' encoding is an NxL matrix where element [n][l]
# is the symbol index for character at index (l) of sentence (n)
# (e.g., say, 5, corresponding to 'e').
#
# The one-hot encoding is an NxLxS matrix, where S is the 
# number of symbols in the alphabet, such that element [n][l][s]
# is 1 if the character at index (l) in sentence (n) has the
# symbol index (s), and 0 otherwise.
def onehot_encode(sentence, maxlen):
    x = np.zeros((maxlen, len(chars)), dtype=np.bool)
    for t, char in enumerate(sentence):
        x[t, char_indices[char]] = 1
    return x

x = np.zeros((len(sentences), maxlen, len(chars)), dtype=np.bool)
y = np.zeros((len(sentences), len(chars)), dtype=np.bool)
for i, sentence in enumerate(sentences):
    x[i,:,:] = onehot_encode(sentence, maxlen)
    y[i, :] = onehot_encode(next_chars[i], 1)

print(x.shape)
print(y.shape)
In [ ]:
# Build the generator model: a single GRU layer with 128 cells.
generator_model = Sequential()
generator_model.add(GRU(128, input_shape=(maxlen, len(chars))))
generator_model.add(Dense(len(chars)))
generator_model.add(Activation('softmax'))

# You could experiment with NAdam instead of RMSProp.
optimizer = RMSprop(lr=0.01)
generator_model.compile(loss='categorical_crossentropy', optimizer=optimizer)
trained_epochs = 0
In [ ]:
def generate_sentence_list(seed_list, length=400, temperature=0.25):
    sentence_list = [];
    generated_list = [];
    n = len(seed_list)
    # copy lists
    for seed in seed_list:
        sentence_list.append(seed[:])
        generated_list.append(seed[:])    
    
    for i in range(length):
      
        workdone = (i+1)*1.0 / length
        sys.stdout.write("\rgenerating sentences: [{0:20s}] {1:.1f}%".format('#' * int(workdone * 20), workdone*100))
        sys.stdout.flush()
            
        x_pred_list = np.zeros((n, maxlen, len(chars)))
        for j, sentence in enumerate(sentence_list):
            for t, char in enumerate(sentence):
                x_pred_list[j, t, char_indices[char]] = 1.

        start = time.time()
        pred_list = generator_model.predict(x_pred_list, verbose=0)
        end = time.time()

        for j in range(n):
            next_index = sample(pred_list[j,:], temperature)
            next_char = indices_char[next_index]
            generated_list[j] += next_char
            sentence_list[j] = sentence_list[j][1:] + next_char
    
    sys.stdout.write(' - done\n')
    sys.stdout.flush()
    
    return generated_list

def print_sentences(seeds, sentences):
    for seed, sentence in zip(seeds, sentences):
        print('-'*5)
        sys.stdout.write('\x1b[32m')
        sys.stdout.write(sentence[0:len(seed)])
        sys.stdout.write('\x1b[34m')
        sys.stdout.write(sentence[len(seed):-1])
        sys.stdout.write('\x1b[m')
        sys.stdout.write('\n')    
        sys.stdout.flush()
        
def pick_sentences(n, maxlen):
    global text    
    start_index_list = np.random.randint(len(text) - maxlen - 1, size=(1, n)).flatten().tolist()
    seed_list = [] 
    for start_index in start_index_list:
        seed_list.append(text[start_index: start_index + maxlen])
    return seed_list
In [ ]:
# Generate 3 seeds which we will use to inspect the progress of our training:
preview_seeds = pick_sentences(3, maxlen=40)

# Train the model, output generated text after each iteration
for iteration in range(1, 10):
    print()
    print('-' * 50)
    print('Iteration', iteration)
    generator_model.fit(x, y,
                  batch_size=1024,
                  epochs=4)

    generated_sentences = generate_sentence_list(preview_seeds)
    print_sentences(preview_seeds, generated_sentences)
In [ ]:
# For a more complete inspection, print out a load of sentences:
#
num_sentences = 100             # how many to generate
sentence_length = 250            # 100--400 is good
sample_temperature = 0.25       # see discussion of temperature up near the top

start_index_list = np.random.randint(len(text) - maxlen - 1, size=(1, num_sentences)).flatten().tolist()
preview_seeds = [] 
for start_index in start_index_list:
    preview_seeds.append(text[start_index: start_index + maxlen])

generated_sentences = generate_sentence_list(preview_seeds, length=sentence_length, temperature=sample_temperature); 
print_sentences(preview_seeds, generated_sentences)
In [ ]:
# This is just a checkpoint, which will let you download and re-upload (or add to git) this model.
save_model(generator_model, './generator_model.h5')
In [ ]:
# Generating the training fake sentences for the Discriminator network
#
# These are saved to the file 'fake.pkl' -- you could download this to your
# user drive and re-upload it in a subsequent session, to save regenerating
# it again (in which case you don't need to evaluate this cell).

training_seeds = pick_sentences(3000, maxlen=40)
training_generated_sentences = generate_sentence_list(training_seeds, length=40)
training_generated_sentences+= generate_sentence_list(training_seeds, length=40,temperature=0.1)
training_generated_sentences+= generate_sentence_list(training_seeds, length=40,temperature=0.5)
# Strip out the initial 40 chars (the seed sequence, which is genuine data from the corpus).
for i, sentence in enumerate(training_generated_sentences):
    training_generated_sentences[i] = sentence[40:40+40]
    
output = open('fake.pkl', 'wb')
pickle.dump(training_seeds, output)
pickle.dump(training_generated_sentences, output)
output.close()
In [ ]:
# Load the training set from the file
pkl_file = open('fake.pkl', 'rb')
training_seeds = pickle.load(pkl_file)
training_generated_sentences = pickle.load(pkl_file)
pkl_file.close()
In [ ]:
# Make a 50:50 set of 'fake' (generated) and genuine sentences:
num_generated = len(training_generated_sentences)
training_real_sentences =  (num_generated, maxlen=40)

all_training_sentences = training_generated_sentences + training_real_sentences
n = len(all_training_sentences)
x = np.zeros((n, 40, len(chars)))
y = np.zeros((n, 1))

for i, sentence in enumerate(all_training_sentences):
    x[i, :, :] = onehot_encode(sentence, maxlen=40)
y[num_generated:] = 1  # Encodes the fact that sentences with indexes larger than (num_generated) are real.
In [ ]:
print('Build model...')

# Define some layers here..

# Use your layers to create the model.
discriminator_model = Sequential()
discriminator_model.add(LSTM(128,input_shape=(maxlen,len(chars))))
discriminator_model.add(Dense(1,activation='sigmoid'))
opt = RMSprop(lr=0.01)

# Setup the optimisation strategy.
discriminator_model.compile(optimizer='Nadam',
                    loss='binary_crossentropy',
                    metrics=['accuracy'])
                             
print('compiled.')
discriminator_model.summary()
In [ ]:
[x_train, x_test, y_train, y_test] = train_test_split(x, y, test_size=0.33, random_state=42)
discriminator_model.fit(x_train, y_train, validation_data=(x_test, y_test), epochs=4, batch_size=64) 
In [ ]:
# Once you're happy with your discriminator model, evaluate this cell to save it:
save_model(discriminator_model, './discriminator_model.h5')
# Run these commands in the terminal to submit your model for assessment.
# git add lab-07/discriminator_model.h5
# git commit -m "Add/update discriminator model."
# git push
# submit-lab 7