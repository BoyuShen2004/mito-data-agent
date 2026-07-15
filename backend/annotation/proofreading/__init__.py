"""Online-proofreading provider boundary.

The application integrates with a proofreading/visualization tool through this
small interface, so the actual editor (an external tool, Neuroglancer, a custom
React editor, desktop software) can change without touching task-detail or
submission flows. The MVP ships placeholder / external-link / Neuroglancer
adapters; none implement in-browser voxel editing.

To change online proofreading → edit files in this package, and
``frontend/src/features/proofreading/`` on the client.
"""
