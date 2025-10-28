<p align="center">
  <img src="https://github.com/user-attachments/assets/b93fd630-6379-4c4f-b77b-96e9ab00f7c4" alt="Adopt_fulllogo" width="300"/>
</p>

<br><br>

Input data and code for "Unlocking the green power of the North Sea: Identifying key energy infrastructure synergies for 2030 and 2040"
--------------------------------
This package contains all input data and code required to run the optimizations
presented in the paper. Below a short overview of the repository.

- mes_north_sea contains data and scripts for pre- and postprocessing of input data
- adopt_net0 contains version v0.1.10 of AdOpT-NET0
- main2030_cost.py is the main script to run the cost optimizations for the 2030 scenarios
- main2030_emission_reduction.py is the main script to run the emission reduction optimizations for the 2030 scenarios
- main2040.py is the main script to run the optimizations for the 2040 scenarios

All main scripts rely heavily on help functions that
can be found in mes_north_sea/optimization/utilities

The results can be found on a ZENODO repository [here](https://doi.org/10.5281/zenodo.14336316).
The visualization app is available [here](https://vis-systemintegration-northsea.streamlit.app/) with the [GitHub repository here](https://github.com/UU-ER/Key-Infrastructure-North-Sea-Visualization).
