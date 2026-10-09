Research question: Does simple data augmentation improve the test accuracy of a convolutional neural network on Fashion-MNIST?

Keep the research relatively simple, scientifically rigorous, and computationally manageable. The study should investigate whether applying basic image augmentation during training improves a CNN's generalization performance compared with training the same CNN without augmentation.

Experimental requirements:
- Dataset: Fashion-MNIST.
- Framework: PyTorch.
- Model: A small CNN suitable for fast training.
- Conditions: Standard training versus training with basic image augmentation.
- Augmentation: Use simple, reasonable transformations such as small random translations or rotations.
- Training: Approximately 5 epochs per condition.
- Random seeds: 42 and 123, for both conditions.
- Keep the architecture, optimizer, learning rate, training/validation split, and other relevant hyperparameters identical between conditions.
- Evaluate test accuracy, training/validation performance, and differences between conditions.
- Generate relevant experimental figures and tables.
- Do not overstate statistical significance with only two seeds.
- Use real literature sources, real computations, and real experimental outputs.
- Compute: the neural network training runs must execute on a CUDA GPU through Google Colab (T4 or L4) using the GPU job tool, and must record evidence that PyTorch detected the CUDA GPU and trained on it. Do not substitute CPU training. Ordinary Python, data processing and plotting may run in the regular CPU sandbox.

Keep the project focused. Do not expand it into a large hyperparameter search or extensive benchmark study.
