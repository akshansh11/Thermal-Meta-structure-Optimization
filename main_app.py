# -*- coding: utf-8 -*-
"""main_app.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1j3jJJl20GEbevzRJwVQBgx4YuFixSM5W
"""

import streamlit as st
import numpy as np
from scipy.sparse import csc_matrix, diags
from scipy.sparse.linalg import spsolve
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
import io
from matplotlib.colors import LinearSegmentedColormap

class ThermalTopologyOptimization:
    def __init__(self, nelx, nely, volfrac, penal, rmin):
        self.nelx = nelx
        self.nely = nely
        self.volfrac = volfrac
        self.penal = penal
        self.rmin = rmin
        self.x = volfrac * np.ones(nely*nelx)
        self.dc = np.zeros(nely*nelx)
        self.ke = self.lk()
        self.iter = 0

    def lk(self):
        k = np.array([
            [2/3, -1/6, -1/3, -1/6],
            [-1/6, 2/3, -1/6, -1/3],
            [-1/3, -1/6, 2/3, -1/6],
            [-1/6, -1/3, -1/6, 2/3]
        ])
        return k

    def FE(self, x):
        K = self.assemble_K(x)
        F = self.load_vector()
        K = K + diags(np.ones(K.shape[0]) * 1e-9)
        try:
            U = spsolve(K, F)
        except:
            st.warning("Solver failed, using approximate solution")
            U = np.zeros_like(F)
        return U

    def assemble_K(self, x):
        KE = self.ke
        nDof = 2*(self.nelx+1)*(self.nely+1)
        K = np.zeros((nDof, nDof))

        for ely in range(self.nely):
            for elx in range(self.nelx):
                n1 = (self.nely+1)*elx + ely
                n2 = (self.nely+1)*(elx+1) + ely
                edof = np.array([n1, n2, n2+1, n1+1])

                ke = KE * (0.001 + 0.999*x[ely*self.nelx + elx]**self.penal)

                for i in range(4):
                    for j in range(4):
                        K[edof[i], edof[j]] += ke[i,j]

        return csc_matrix(K)

    def load_vector(self):
        F = np.zeros(2*(self.nelx+1)*(self.nely+1))
        F[0] = 1.0
        F[-1] = -1.0
        return F

    def compute_compliance(self, x, u):
        ce = np.zeros(self.nely*self.nelx)
        for ely in range(self.nely):
            for elx in range(self.nelx):
                n1 = (self.nely+1)*elx + ely
                n2 = (self.nely+1)*(elx+1) + ely
                edof = np.array([n1, n2, n2+1, n1+1])
                Ue = u[edof]
                ce[ely*self.nelx + elx] = np.dot(np.dot(Ue, self.ke), Ue)
        return ce

    def filter_sensitivity(self, dc):
        filtered_dc = np.zeros_like(dc)
        for i in range(self.nely):
            for j in range(self.nelx):
                sum_weight = 0.0
                for k in range(max(0, i-int(self.rmin)), min(self.nely, i+int(self.rmin)+1)):
                    for l in range(max(0, j-int(self.rmin)), min(self.nelx, j+int(self.rmin)+1)):
                        fac = self.rmin - np.sqrt((i-k)**2 + (j-l)**2)
                        if fac > 0:
                            sum_weight += fac
                            filtered_dc[i*self.nelx + j] += fac * dc[k*self.nelx + l]
                filtered_dc[i*self.nelx + j] /= max(1e-3, sum_weight)
        return filtered_dc

    def OC(self, x, dc):
        l1, l2 = 0, 1e9
        move = 0.2
        xnew = np.zeros(self.nelx*self.nely)

        while abs(l2-l1) > 1e-4:
            lmid = 0.5*(l2+l1)
            xnew = np.maximum(0.001, np.maximum(x-move,
                   np.minimum(1.0, np.minimum(x+move,
                   x*np.sqrt(np.maximum(1e-10, -dc/(lmid + 1e-10))))))
            )

            if np.sum(xnew) - self.volfrac*self.nelx*self.nely > 0:
                l1 = lmid
            else:
                l2 = lmid

            if l1 == l2:
                break

        return xnew

    def plot(self, x, fig, ax):
        ax.clear()
        im = ax.imshow(x.reshape(self.nely, self.nelx),
                      cmap='magma',
                      interpolation='none',
                      vmin=0, vmax=1)
        plt.colorbar(im, ax=ax, label='Material Density')
        ax.set_title(f'Thermal Meta-structure Design\nIteration {self.iter}')
        ax.set_xlabel('X coordinate')
        ax.set_ylabel('Y coordinate')
        return im

    def optimize_with_animation(self, progress_bar):
        frames = []
        loop = 0
        change = 1
        maxiter = 100

        fig, ax = plt.subplots(figsize=(10, 6))

        while change > 0.01 and loop < maxiter:
            loop += 1
            self.iter = loop

            U = self.FE(self.x)
            c = np.sum(self.compute_compliance(self.x, U))
            dc = -self.penal * (self.x**(self.penal-1)) * self.compute_compliance(self.x, U)
            dc = self.filter_sensitivity(dc)

            xold = self.x.copy()
            self.x = self.OC(self.x, dc)

            change = np.linalg.norm(self.x - xold)/np.linalg.norm(self.x)

            frames.append(self.x.copy())
            progress_bar.progress(loop/maxiter)

        anim = FuncAnimation(
            fig,
            lambda frame: self.plot(frames[frame], fig, ax),
            frames=len(frames),
            interval=100,
            blit=False
        )

        writer = PillowWriter(fps=10)
        plt.close()
        return anim, writer

def main():
    st.set_page_config(page_title="Thermal Meta-structure Optimization", layout="wide")

    st.title("Thermal Meta-structure Topology Optimization")
    st.markdown("""
    This app performs topology optimization for thermal meta-structures.
    Adjust the parameters below and click 'Optimize' to see the evolution of the design.
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        nelx = st.slider("Width (elements)", 20, 100, 60, help="Number of elements in x direction")
        nely = st.slider("Height (elements)", 20, 100, 30, help="Number of elements in y direction")

    with col2:
        volfrac = st.slider("Volume Fraction", 0.1, 0.9, 0.4, help="Fraction of material to be used")
        penal = st.slider("Penalization", 1.0, 5.0, 3.0, help="Penalization parameter for SIMP")

    with col3:
        rmin = st.slider("Filter Radius", 1.0, 3.0, 1.5, help="Radius of sensitivity filter")

    if st.button("Optimize", type="primary"):
        optimizer = ThermalTopologyOptimization(nelx, nely, volfrac, penal, rmin)

        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.text('Optimizing...')
        anim, writer = optimizer.optimize_with_animation(progress_bar)

        # Save animation
        f = io.BytesIO()
        anim.save(f, writer=writer)
        status_text.text('Optimization complete!')

        # Display animation
        st.image(f.getvalue(), caption='Optimization Progress', use_column_width=True)

        # Download button
        btn = st.download_button(
            label="Download Animation",
            data=f.getvalue(),
            file_name="topology_optimization.gif",
            mime="image/gif"
        )

if __name__ == "__main__":
    main()