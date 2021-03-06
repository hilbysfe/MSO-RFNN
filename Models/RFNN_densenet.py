import numpy as np
import tensorflow as tf

from Utils.rfnn_utils import init_basis_hermite_2D
from Utils.rfnn_utils import init_basis_hermite_steerable_2D

# single scale/orientation
from Utils.rfnn_utils import _rfnn_conv_layer_pure_2d

# multi-scale/orientation keeping output
from Utils.rfnn_utils import _rfnn_conv_layer_pure_2d_MSO_avg
from Utils.rfnn_utils import _rfnn_conv_layer_pure_2d_MSO_max
from Utils.rfnn_utils import _rfnn_conv_layer_pure_2d_MSO_learn_fl_bc
from Utils.rfnn_utils import _rfnn_conv_layer_pure_2d_MSO_learn_sq_bc
from Utils.rfnn_utils import _rfnn_conv_layer_pure_2d_MSO_learn_flatten

from Utils.cnn_utils import _conv_layer_pure_2d

TF_VERSION = float('.'.join(tf.__version__.split('.')[:2]))

class RFNNDenseNet(object):
	def __init__(self, is_training,
					init_sigmas='2.0,1.5',
					comp_sigmas='1.0,0.5',
					init_order=3,
					comp_order=3,
					thetas='45,45',
					rfnn='learn_sq',
					growth_rate = 8,
					depth = 21,
					total_blocks = 4,
					keep_prob = 0.9,
					model_type = 'DenseNet',
					init_kernel = 11,
					comp_kernel = 5,
					bnorm_momentum = 0.7,
					renorm = 0.7,
					reduction = 0.5,
					bc_mode = True,
					beta_wd = 1e-4,
					avgpool_kernel_ratio = 0.5,
					avgpool_stride_ratio = 0.5,
					n_classes = 2
				):

		self.kernels = []
		self.alphas = []
		self.conv_act = []
#		self.bc_conv_act = []
#		self.bc_weights = []
		self.weights = []
		self.fl_act = []
		self.bnorm_momentum = bnorm_momentum
		self.renorm = renorm
		self.beta_wd = beta_wd

		self.n_classes = n_classes
		self.depth = depth
		self.growth_rate = growth_rate
		self.bc_mode = bc_mode
		self.avgpool_kernel_ratio = avgpool_kernel_ratio
		self.avgpool_stride_ratio = avgpool_stride_ratio

		self.variable_dict = dict()

		# how many features will be received after first convolution
		# value the same as in the original Torch code
		if self.bc_mode:
			self.first_output_features = growth_rate * 2
		else:
			self.first_output_features = 16
		self.total_blocks = total_blocks
		self.layers_per_block = (depth - (total_blocks + 1)) // total_blocks

		# compression rate at the transition layers
		self.reduction = reduction
		self.is_training = is_training

		self.initial_kernel = init_kernel
		self.comp_kernel = comp_kernel
		self.init_sigmas = init_sigmas
		self.comp_sigmas = comp_sigmas
		self.thetas = thetas

		self.hermit_initial = init_basis_hermite_steerable_2D(self.initial_kernel, self.init_sigmas, theta=self.thetas[0], order=init_order) \
			if rfnn is not "single" else init_basis_hermite_2D(self.initial_kernel, self.init_sigmas[0], init_order)
		self.hermit_composite = init_basis_hermite_steerable_2D(self.comp_kernel, self.comp_sigmas, theta=self.thetas[1], order=comp_order) \
			if rfnn is not "single" else init_basis_hermite_2D(self.comp_kernel, self.comp_sigmas[0], comp_order)

		self.rfnn_layer = \
			_rfnn_conv_layer_pure_2d_SO_learn_fl_bc if rfnn=="learn_fl" else \
			_rfnn_conv_layer_pure_2d_SO_learn_sq_bc if rfnn=="learn_sq" else \
			_rfnn_conv_layer_pure_2d_SO_avg if rfnn=="avg" else \
			_rfnn_conv_layer_pure_2d_SO_max if rfnn=="max" else \
			_rfnn_conv_layer_pure_2d_SO_learn_flatten if rfnn=="flatten" else \
			_rfnn_conv_layer_pure_2d

		if not bc_mode:
			print("Build %s model with %d blocks, "
				  "%d composite layers each." % (
					  model_type, self.total_blocks, self.layers_per_block))
		if bc_mode:
			self.layers_per_block = self.layers_per_block // 2
			print("Build %s model with %d blocks, "
				  "%d bottleneck layers and %d composite layers each." % (
					  model_type, self.total_blocks, self.layers_per_block,
					  self.layers_per_block))
		print("Reduction at transition layers: %.1f" % self.reduction)

		self.keep_prob = keep_prob
		self.model_type = model_type

	def _count_trainable_params(self):
		total_parameters = 0
		for variable in tf.trainable_variables():
			shape = variable.get_shape()
			variable_parametes = 1
			for dim in shape:
				variable_parametes *= dim.value
			total_parameters += variable_parametes
		if total_parameters / 1e6 < 1:
			print("Total training params: %.1fK" % (total_parameters / 1e3))
		else:
			print("Total training params: %.1fM" % (total_parameters / 1e6))

	def composite_function(self, _input, out_features, kernel_size=3):
		"""Function from paper H_l that performs:
		- batch normalization
		- ReLU nonlinearity
		- convolution with required kernel
		- dropout, if required
		"""
		with tf.variable_scope("composite_function") as scope:
			# BN
			output = self.batch_norm(output)
			# ReLU
			output = tf.nn.relu(output)
			# convolution
			if kernel_size == 1:
				output, weights = _conv_layer_pure_2d(output, shape=[1, 1, output.get_shape()[-1].value, out_features], padding='VALID')
#				self.bc_weights.append(weights)
#				self.bc_conv_act.append(output)
				self.variable_dict[scope.name + '_weights'] = weights
			else:
				output, alphas, kernel, scale_bc = self.rfnn_layer(output, self.hermit_composite, out_features,
												 self.is_training, self.bnorm_momentum, self.renorm)
#				self.kernels.append(kernel)
				self.alphas.append(alphas)
				self.conv_act.append(output)
				self.variable_dict[scope.name+'_alphas'] = alphas
				self.variable_dict[scope.name + '_scale_bc'] = scale_bc
			# dropout(in case of training and in case it is no 1.0)
			output = self.dropout(output)
		return output

	def bottleneck(self, _input, out_features):
		with tf.variable_scope("bottleneck") as scope:
			# BN
			output = self.batch_norm(_input)
			# ReLU
			output = tf.nn.relu(output)
			inter_features = out_features * 4
			# 1x1 convolution
			output, weights = _conv_layer_pure_2d(output, shape=[1, 1, output.get_shape()[-1].value, inter_features], padding='VALID')
#			self.bc_conv_act.append(output)
#			self.bc_weights.append(weights)
			self.variable_dict[scope.name] = weights
		output = self.dropout(output)
		return output

	def add_internal_layer(self, _input, growth_rate):
		"""Perform H_l composite function for the layer and after concatenate
		input with output from composite function.
		"""
		# call composite function with 3x3 kernel
		if not self.bc_mode:
			comp_out = self.composite_function(
				_input, out_features=growth_rate, kernel_size=self.comp_kernel)
		elif self.bc_mode:
			bottleneck_out = self.bottleneck(_input, out_features=growth_rate)
			comp_out = self.composite_function(
				bottleneck_out, out_features=growth_rate, kernel_size=self.comp_kernel)
		# concatenate _input with out from composite function
		if TF_VERSION >= 1.0:
			output = tf.concat(axis=3, values=(_input, comp_out))
		else:
			output = tf.concat(3, (_input, comp_out))
		return output

	def add_block(self, _input, growth_rate, layers_per_block):
		"""Add N H_l internal layers"""
		output = _input
		for layer in range(layers_per_block):
			with tf.variable_scope("layer_%d" % layer):
				output = self.add_internal_layer(output, growth_rate)
		print(output.get_shape())
		return output

	def transition_layer(self, _input):
		"""Call H_l composite function with 1x1 kernel and after average
		pooling
		"""
		# call composite function with 1x1 kernel
		out_features = int(int(_input.get_shape()[-1]) * self.reduction)
		output = self.composite_function(
			_input, out_features=out_features, kernel_size=1)
		print(output.get_shape())
		# run average pooling
		output = self.avg_pool(output, k=2, s=2)
		print(output.get_shape())
		return output

	def transition_layer_to_classes(self, _input, scope):
		"""This is last transition to get probabilities by classes. It perform:
		- batch normalization
		- ReLU nonlinearity
		- wide average pooling
		- FC layer multiplication
		"""
		# BN
		output = self.batch_norm(_input)
		# ReLU
		output = tf.nn.relu(output)
		self.penultimate = output
		# average pooling
		last_pool_kernel = [1, int(output.get_shape()[1].value), int(output.get_shape()[2]) * self.avgpool_kernel_ratio, 1]
		last_pool_stride = [1, int(output.get_shape()[1].value), int(output.get_shape()[2]) * self.avgpool_stride_ratio, 1]
		output = tf.nn.avg_pool(output, last_pool_kernel, last_pool_stride, 'VALID')
		print(output.get_shape())
		# FC
		features_total = int(output.get_shape()[-1])*int(output.get_shape()[-2])
		output = tf.reshape(output, [-1, features_total])
#		self.penultimate = output
		W = self.weight_variable_xavier(
			[features_total, self.n_classes], name='W')
		self.weights.append(W)
		self.variable_dict[scope.name + '_weights'] = W
		bias = self.bias_variable([self.n_classes])
		self.variable_dict[scope.name + '_bias'] = bias
		logits = tf.matmul(output, W) + bias
		self.fl_act.append(logits)

		return logits

	def avg_pool(self, _input, k, s):
		ksize = [1, k, k, 1]
		strides = [1, s, s, 1]
		padding = 'VALID'
		output = tf.nn.avg_pool(_input, ksize, strides, padding)
		return output

	def batch_norm(self, _input):
		output = tf.contrib.layers.batch_norm(
			_input, decay=self.bnorm_momentum, is_training=self.is_training, center=False,
			renorm=True, renorm_decay=self.renorm)#, param_regularizers={'beta': tf.contrib.layers.l2_regularizer(self.beta_wd)})
		return output

	def dropout(self, _input):
		if self.keep_prob < 1:
			output = tf.cond(
				self.is_training,
				lambda: tf.nn.dropout(_input, self.keep_prob),
				lambda: _input
			)
		else:
			output = _input
		return output

	def weight_variable_msra(self, shape, name):
		return tf.get_variable(
			name=name,
			shape=shape,
			initializer=tf.contrib.layers.variance_scaling_initializer())

	def weight_variable_xavier(self, shape, name):
		return tf.get_variable(
			name,
			shape=shape,
			initializer=tf.contrib.layers.xavier_initializer())

	def bias_variable(self, shape, name='bias'):
		initial = tf.constant(0.0, shape=shape)
		return tf.get_variable(name, initializer=initial)

	def inference(self, X):
		growth_rate = self.growth_rate
		layers_per_block = self.layers_per_block
		# first - initial 3 x 3 conv to first_output_features
		with tf.variable_scope("Initial_convolution") as scope:
			output, alphas, kernel, scale_bc = self.rfnn_layer(X, self.hermit_initial, self.first_output_features,
											 self.is_training, self.bnorm_momentum, self.renorm, strides=[1,2,2,1])
			print(output.get_shape())
			self.kernels.append(kernel)
			self.alphas.append(alphas)
			self.conv_act.append(output)

			self.variable_dict[scope.name+'_alphas'] = alphas
			self.variable_dict[scope.name+'_scale_bc'] = scale_bc
		with tf.variable_scope("Initial_pooling"):
			output = tf.nn.max_pool(output, ksize=[1, 3, 3, 1], strides=[1, 2, 2, 1], padding='VALID')
			print(output.get_shape())

		# add N required blocks
		for block in range(self.total_blocks):
			with tf.variable_scope("Block_%d" % block):
				output = self.add_block(output, growth_rate, layers_per_block)
			# last block exist without transition layer
			if block != self.total_blocks - 1:
				with tf.variable_scope("Transition_after_block_%d" % block):
					output = self.transition_layer(output)

		with tf.variable_scope("Transition_to_classes") as scope:
			self.logits = self.transition_layer_to_classes(output, scope)

		self.prob = tf.nn.softmax(self.logits, name="prob")
		self._count_trainable_params()

		return self.logits, self.penultimate, self.prob