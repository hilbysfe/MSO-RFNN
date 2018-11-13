import numpy as np
import tensorflow as tf

CONV_INITIALIZER = tf.contrib.layers.xavier_initializer()
BIAS_INITIALIZER = tf.constant_initializer(0.0)


def _conv_layer_2d(input, shape, strides, padding, is_training, bnorm=False):
	# 
	kernel = tf.get_variable(
		'weights',
		shape,
		initializer=CONV_INITIALIZER,
		dtype=tf.float32)
	# No bias when BN
	if not bnorm:
		biases = tf.get_variable(
			'biases',
			[shape[-1]],
			initializer=tf.constant_initializer(0.0),
			dtype=tf.float32)

	conv = tf.nn.conv2d(input, kernel, strides=strides, padding=padding, name='Pre-Activation')

	if bnorm:
		conv = batch_norm(conv, is_training)
	else:
		conv = tf.nn.bias_add(conv, biases)

	conv_out = tf.nn.relu(conv, name='Activation')

	with tf.variable_scope('/visualization'):
		# scale weights to [0 1], type is still float
		kernel_avg = tf.reduce_mean(kernel, axis=2)
		x_min = tf.reduce_min(kernel_avg)
		x_max = tf.reduce_max(kernel_avg)
		kernel_0_to_1 = (kernel_avg - x_min) / (x_max - x_min)

		# to tf.image_summary format [channels, height, width]
		kernel_transposed = tf.transpose(kernel_0_to_1, [2, 0, 1])
		kernel_transposed = tf.expand_dims(kernel_transposed, axis=3)
		channels = kernel_transposed.get_shape()[0].value

		tf.summary.image('filters', kernel_transposed, max_outputs=channels)

		conv_transposed = tf.transpose(conv_out[0], [2, 0, 1])
		conv_transposed = tf.expand_dims(conv_transposed, axis=3)
		tf.summary.image('activation', conv_transposed, max_outputs=channels)

		return conv_out

def _conv_layer_pure_2d(input, shape, strides=[1, 1, 1, 1], padding='SAME'):
	kernel = tf.get_variable(
		'weights',
		shape,
		initializer=tf.contrib.layers.variance_scaling_initializer(),
		dtype=tf.float32)

	conv = tf.nn.conv2d(input, kernel, strides=strides, padding=padding, name='Pre-Activation')

#	with tf.variable_scope('/visualization'):
#		# scale weights to [0 1], type is still float
#		kernel_avg = tf.reduce_mean(kernel, axis=2)
#		x_min = tf.reduce_min(kernel_avg)
#		x_max = tf.reduce_max(kernel_avg)
#		kernel_0_to_1 = (kernel_avg - x_min) / (x_max - x_min)

		# to tf.image_summary format [channels, height, width]
#		kernel_transposed = tf.transpose(kernel_0_to_1, [2, 0, 1])
#		kernel_transposed = tf.expand_dims(kernel_transposed, axis=3)
#		channels = kernel_transposed.get_shape()[0].value
#
#		tf.summary.image('filters', kernel_transposed, max_outputs=channels)
#
#		conv_transposed = tf.transpose(conv[0], [2, 0, 1])
#		conv_transposed = tf.expand_dims(conv_transposed, axis=3)
#		tf.summary.image('activation', conv_transposed, max_outputs=channels)

	return conv, kernel

def _conv_layer_2d_with_kernel(input, kernel, strides, padding, is_training, name, bnorm=False):
	# No bias when BN
	if not bnorm:
		biases = tf.get_variable(
			'biases',
			[kernel.get_shape()[-1]],
			initializer=BIAS_INITIALIZER,
			dtype=tf.float32)

	conv = tf.nn.conv2d(input, kernel, strides=strides, padding=padding, name='Pre-Activation')

	if bnorm:
		conv = batch_norm_wrapper(conv, is_training, True)
	else:
		conv = tf.nn.bias_add(conv, biases)

	conv_out = tf.nn.relu(conv, name='Activation')

	with tf.variable_scope('Visualization'):
		# scale weights to [0 1], type is still float
		kernel_avg = tf.reduce_mean(kernel, axis=2)
		x_min = tf.reduce_min(kernel_avg)
		x_max = tf.reduce_max(kernel_avg)
		kernel_0_to_1 = (kernel_avg - x_min) / (x_max - x_min)

		# to tf.image_summary format [batch_size, height, width, channels]
		kernel_transposed = tf.transpose(kernel_0_to_1, [2, 0, 1])
		kernel_transposed = tf.expand_dims(kernel_transposed, axis=3)
		batch = kernel_transposed.get_shape()[0].value

		tf.summary.image('Filters', kernel_transposed, max_outputs=batch)

	return conv_out

def _conv_layer_2d_with_kernel_and_bias(input, kernel, biases, strides, padding, is_training, bnorm=False):
	conv = tf.nn.conv2d(input, kernel, strides=strides, padding=padding, name='Pre-Activation')

	# No bias when BN
	if bnorm:
		conv = batch_norm_wrapper(conv, is_training, True)
	else:
		conv = tf.nn.bias_add(conv, biases)

	conv_out = tf.nn.relu(conv, name='Activation')

	with tf.variable_scope('Visualization'):
		# scale weights to [0 1], type is still float
		kernel_avg = tf.reduce_mean(kernel, axis=2)
		x_min = tf.reduce_min(kernel_avg)
		x_max = tf.reduce_max(kernel_avg)
		kernel_0_to_1 = (kernel_avg - x_min) / (x_max - x_min)

		# to tf.image_summary format [batch_size, height, width, channels]
		kernel_transposed = tf.transpose(kernel_0_to_1, [2, 0, 1])
		kernel_transposed = tf.expand_dims(kernel_transposed, axis=3)
		batch = kernel_transposed.get_shape()[0].value

		tf.summary.image('Filters', kernel_transposed, max_outputs=batch)

	return conv_out

def _conv_layer_3d(input, shape, strides, padding, is_training, bnorm=False):
	kernel = tf.get_variable(
		'weights',
		shape,
		initializer=CONV_INITIALIZER,
		dtype=tf.float32)
	# No bias when BN
	if not bnorm:
		biases = tf.get_variable(
			'biases',
			[shape[-1]],
			initializer=BIAS_INITIALIZER,
			dtype=tf.float32)

	conv = tf.nn.conv3d(input, kernel, strides=strides, padding=padding)

	if bnorm:
		conv = batch_norm_wrapper(conv, is_training, True)
	else:
		conv = tf.nn.bias_add(conv, biases)

	conv_out = tf.nn.relu(conv, name='Activation')

	return conv_out

def _conv_layer_pure_3d(input, shape, strides=[1, 1, 1, 1, 1], padding='SAME'):
	kernel = tf.get_variable(
		'weights',
		shape,
		initializer=tf.contrib.layers.variance_scaling_initializer(),
		dtype=tf.float32)

	conv = tf.nn.conv3d(input, kernel, strides=strides, padding=padding, name='Pre-Activation')

	return conv, kernel

def _conv_layer_3d_with_kernel(input, kernel, shape, strides, padding, is_training, bnorm=False):
	# No bias when BN
	if not bnorm:
		biases = tf.get_variable(
			'biases',
			[shape[-1]],
			initializer=BIAS_INITIALIZER,
			dtype=tf.float32)

	conv = tf.nn.conv3d(input, kernel, strides=strides, padding=padding)

	if bnorm:
		conv = batch_norm_wrapper(conv, is_training, True)
	else:
		conv = tf.nn.bias_add(conv, biases)

	conv_out = tf.nn.relu(conv, name='Activation')

	return conv_out


def _full_layer(input, shape, act, is_training, regularizer, bnorm=False):
	weights = tf.get_variable(
		'weights',
		shape=shape,
		initializer=tf.truncated_normal_initializer(stddev=np.sqrt(2 / shape[-1]), dtype=tf.float32),
		regularizer=regularizer)
	# No bias when BN
	if not bnorm:
		biases = tf.get_variable(
			'biases',
			[shape[-1]],
			initializer=BIAS_INITIALIZER,
			dtype=tf.float32)

	wx = tf.matmul(input, weights)
	if bnorm:
		wx = batch_norm_wrapper(wx, is_training, False)
	else:
		wx = tf.nn.bias_add(wx, biases)

	local = act(wx, name="Activation")

	return local

def _softmax_layer(input, shape, is_training, bnorm=False):
	weights = tf.get_variable(
		'weights',
		shape=shape,
		initializer=tf.truncated_normal_initializer(stddev=0.04, dtype=tf.float32),
		regularizer=None)
	# No bias when BN				
	if not bnorm:
		biases = tf.get_variable(
			'biases',
			[shape[-1]],
			initializer=BIAS_INITIALIZER,
			dtype=tf.float32)

	wx = tf.matmul(input, weights, name="Activation")
	if bnorm:
		wx = batch_norm(wx, is_training)
	else:
		wx = tf.nn.bias_add(wx, biases)

	return wx

def batch_norm(_inputs, is_training):
	output = tf.contrib.layers.batch_norm(
		_inputs, scale=True, is_training=is_training,
		updates_collections=None)
	return output
