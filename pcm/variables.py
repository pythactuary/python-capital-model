from __future__ import annotations
from typing import Union
from .frequency_severity import FreqSevSims
from .stochastic_scalar import StochasticScalar, ProteusStochasticVariable
import numpy as np
import scipy.stats
import pandas as pd
import plotly.graph_objects as go
from typing import Union


class ProteusVariable:
    """A class to hold a multivariate variable in a simulation.

    A Proteus Variable is a hierarchical structure that can hold multiple
    scalar variables. The purpose of this class is to allow
    for the creation of more complex variables that can be used in
    simulations.

    Each level of a Proteus Variable can be a list or dictionary of scalar variables or other ProteusVariable objects. Each level can have a different number of elements.
    Each level has a name that can be used to access the level in the hierarchy.

    Sub elements of a ProteusVariable can be accessed using the [] notation.

    """

    def __len__(self):
        return len(self.values)

    def __init__(
        self,
        dim_name: str,
        values: (
            list[Union[ProteusVariable, StochasticScalar | FreqSevSims | float | int]]
            | dict[
                str,
                Union[ProteusVariable, StochasticScalar | FreqSevSims | float | int],
            ]
        ),
    ):
        self.dim_name: str = dim_name
        self.values = values
        self.dimensions = [dim_name]
        self._dimension_set = set(self.dimensions)
        # check the number of simulations in each variable
        self.n_sims = None
        for value in (
            self.values.values() if isinstance(self.values, dict) else self.values
        ):
            if isinstance(value, ProteusVariable):
                if (
                    self._dimension_set.intersection(value._dimension_set)
                    or self.dim_name == value.dim_name
                ):
                    raise ValueError(
                        "Duplicate dimension names in ProteusVariable hierarchy."
                    )
                self._dimension_set.intersection_update(value.dimensions)
                self.dimensions.extend(value.dimensions)

            if self.n_sims is None:
                if isinstance(value, ProteusStochasticVariable):
                    self.n_sims = value.n_sims
                else:
                    self.n_sims = 1
            elif isinstance(value, ProteusStochasticVariable):
                if value.n_sims != self.n_sims:
                    if self.n_sims == 1:
                        self.n_sims == value.n_sims
                    else:
                        raise ValueError("Number of simulations do not match.")

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        if method != "__call__":
            return NotImplemented

        def recursive_apply(*items):
            # If none of the items is a ProteusVariable (i.e. a container), then
            # assume they are leaf nodes (e.g., numbers or stochastic types) and simply call ufunc.
            if not any(isinstance(item, ProteusVariable) for item in items):
                # For stochastic types that implement __array_ufunc__, this call will
                # automatically delegate to their own __array_ufunc__.
                return ufunc(*items, **kwargs)

            # Otherwise, at least one of the items is a container.
            # We assume that the container structure is consistent across items.
            first = items[0]
            if isinstance(first, ProteusVariable):
                # Process dictionary containers.
                if isinstance(first.values, dict):
                    new_data = {}
                    # Iterate over each key in the container.
                    for key in first.values:
                        new_items = []
                        for item in items:
                            if isinstance(item, ProteusVariable):
                                new_items.append(item.values[key])
                            else:
                                new_items.append(item)
                        new_data[key] = recursive_apply(*new_items)
                    return ProteusVariable(first.dim_name, new_data)
                # Process list containers.
                elif isinstance(first.values, list):
                    new_list = []
                    for idx, _ in enumerate(first.values):
                        new_items = []
                        for item in items:
                            if isinstance(item, ProteusVariable):
                                new_items.append(item.values[idx])
                            else:
                                new_items.append(item)
                        new_list.append(recursive_apply(*new_items))
                    return ProteusVariable(first.dim_name, new_list)
                else:
                    # In case data is neither dict nor list, try applying ufunc directly.
                    return ufunc(first.values, **kwargs)
            else:
                # If the first item is not a container but some other item is,
                # we assume they can all be processed by ufunc.
                return ufunc(*items, **kwargs)

        return recursive_apply(*inputs)

    def __array_function__(self, func, types, args, kwargs):
        args = [
            (
                (
                    list(arg.values.values())
                    if isinstance(arg.values, dict)
                    else arg.values
                )
                if isinstance(arg, ProteusVariable)
                else arg
            )
            for arg in args
        ]
        temp = func(*args, **kwargs)
        if isinstance(self.values, dict):
            return ProteusVariable(
                self.dim_name,
                {key: temp[i] for i, key in enumerate(self.values.keys())},
            )
        else:
            return ProteusVariable(self.dim_name, [value for value in temp])

    def sum(self, dimensions: list[str] = []) -> ProteusVariable | StochasticScalar:
        """Sum the variables across the specified dimensions. Returns a new ProteusVariable with the summed values."""
        if dimensions is None or dimensions == []:
            result: StochasticScalar = sum(self)
            return result
        if self.dimensions in dimensions:
            result = ProteusVariable(dim_name=self.values[0].dimensions, values=0)
            for value in self.values:
                if isinstance(value, ProteusVariable | StochasticScalar):
                    result = result + value.sum(dimensions)
                else:
                    result = result + value
            return result
        else:
            return self

    def __iter__(self):
        if isinstance(self.values, dict):
            return iter(self.values.values())
        else:
            return iter(self.values)

    def _binary_operation(self, other, operation):
        if isinstance(other, ProteusVariable):
            if self.dimensions != other.dimensions:
                raise ValueError("Dimensions of the two variables do not match.")
        if isinstance(self.values, dict):
            if isinstance(other, ProteusVariable):
                return ProteusVariable(
                    dim_name=self.dim_name,
                    values={
                        key: operation(value, other.values[key])
                        for key, value in self.values.items()
                    },
                )
            return ProteusVariable(
                dim_name=self.dim_name,
                values={
                    key: operation(value, other) for key, value in self.values.items()
                },
            )
        elif isinstance(self.values, list):
            if isinstance(other, ProteusVariable):
                return ProteusVariable(
                    dim_name=self.dim_name,
                    values=[
                        operation(value, other.values[i])
                        for i, value in enumerate(self.values)
                    ],
                )
            return ProteusVariable(
                dim_name=self.dim_name,
                values=[operation(value, other) for i, value in enumerate(self.values)],
            )

    def __add__(self, other) -> ProteusVariable:
        return self._binary_operation(other, lambda a, b: a + b)

    def __radd__(self, other) -> ProteusVariable:
        return self.__add__(other)

    def __mul__(self, other) -> ProteusVariable:
        return self._binary_operation(other, lambda a, b: a * b)

    def __rmul__(self, other) -> ProteusVariable:
        return self.__mul__(other)

    def __sub__(self, other) -> ProteusVariable:
        return self._binary_operation(other, lambda a, b: a - b)

    def __rsub__(self, other) -> ProteusVariable:
        return self._binary_operation(other, lambda a, b: b - a)

    def __ge__(self, other) -> ProteusVariable:
        return self._binary_operation(other, lambda a, b: a >= b)

    def __le__(self, other) -> ProteusVariable:
        return self._binary_operation(other, lambda a, b: a <= b)

    def __gt__(self, other) -> ProteusVariable:
        return self._binary_operation(other, lambda a, b: a > b)

    def __lt__(self, other) -> ProteusVariable:
        return self._binary_operation(other, lambda a, b: a < b)

    def __rge__(self, other) -> ProteusVariable:
        return self.__lt__(other)

    def __rle__(self, other) -> ProteusVariable:
        return self.__gt__(other)

    def __rgt__(self, other) -> ProteusVariable:
        return self.__le__(other)

    def __rlt__(self, other) -> ProteusVariable:
        return self.__ge__(other)

    def __getitem__(self, key: str | int):
        if isinstance(self.values, dict):
            if isinstance(key, int):
                return self.values[list(self.values.keys())[key]]
            else:
                return self.values[key]
        else:
            if isinstance(key, int):
                return self.values[key]
            else:
                raise ValueError("Key must be an integer for a list.")

    def get_value_at_sim(self, sim_no: int | StochasticScalar):
        _get_value = lambda x: (
            x.get_value_at_sim(sim_no)
            if isinstance(x, ProteusVariable)
            else x[sim_no] if x.n_sims > 1 else x
        )
        if isinstance(self.values, dict):
            result = ProteusVariable(
                dim_name=self.dim_name,
                values={k: _get_value(v) for k, v in self.values.items()},
            )
        elif isinstance(self.values, list):
            result = ProteusVariable(
                dim_name=self.dim_name,
                values=[_get_value(v) for v in self.values],
            )
        return result

    def all(self) -> bool:
        if isinstance(self.values, dict):
            return all([value.all() for value in self.values.values()])
        else:
            return all([value.all() for value in self.values])

    def any(self) -> bool:
        if isinstance(self.values, dict):
            return any([value.any() for value in self.values.values()])
        else:
            return any([value.any() for value in self.values])

    def upsample(self, n_sims: int) -> ProteusVariable:
        """Upsample the variable to the specified number of simulations"""
        if self.n_sims == n_sims:
            return self
        if isinstance(self.values, dict):
            return ProteusVariable(
                dim_name=self.dim_name,
                values={
                    key: (
                        value.upsample(n_sims)
                        if isinstance(value, ProteusStochasticVariable)
                        else value
                    )
                    for key, value in self.values.items()
                },
            )
        else:
            return ProteusVariable(
                dim_name=self.dim_name,
                values=[
                    (
                        value.upsample(n_sims)
                        if isinstance(value, ProteusStochasticVariable)
                        else value
                    )
                    for value in self.values
                ],
            )

    def __eq__(self, other):
        return self._binary_operation(other, lambda a, b: a == b)

    @classmethod
    def from_csv(
        cls,
        file_name: str,
        dim_name: str,
        values_column: str,
        simulation_column="Simulation",
    ) -> ProteusVariable:
        """Import a ProteusVariable from a CSV file.

        Note that only one dimensional variables are supported.
        """
        df = pd.read_csv(file_name)
        pivoted_df = df.pivot(
            index=simulation_column, columns=dim_name, values=values_column
        )
        count = df[dim_name].value_counts()
        pivoted_df.sort_index(inplace=True)

        result = cls(
            dim_name,
            {
                str(label): StochasticScalar(pivoted_df[label].values[: count[label]])
                for label in df[dim_name].unique()
            },
        )
        result.n_sims = max(count)

        return result

    def __repr__(self):
        return f"ProteusVariable(dim_name={self.dim_name}, values={self.values})"

    def correlation_matrix(self, correlation_type="spearman") -> list[list[float]]:
        # validate type
        correlation_type = correlation_type.lower()
        assert correlation_type in ["linear", "spearman", "kendall"]
        assert hasattr(self[0], "values")
        n = len(self.values)
        result: list[list[float]] = [[0.0] * n] * n
        values = [self[i] for i in range(len(self.values))]
        if correlation_type.lower() in ["spearman", "kendall"]:
            # rank the variables first
            for i, value in enumerate(values):
                values[i] = scipy.stats.rankdata(value.values)

        if correlation_type == "kendall":
            for i, value1 in enumerate(values):
                for j, value2 in enumerate(values):
                    result[i][j] = scipy.stats.kendalltau(value1, value2)
        else:
            result = list(np.corrcoef(values))

        return result

    def show_histogram(self):

        fig = go.Figure()
        labels = (
            self.values.keys()
            if isinstance(self.values, dict)
            else range(len(self.values))
        )
        for value, label in zip(self.values.values(), labels):
            fig.add_trace(go.Histogram(x=value.values, name=label))
        fig.show()

    def show_cdf(self):

        fig = go.Figure()
        labels = (
            self.values.keys()
            if isinstance(self.values, dict)
            else range(len(self.values))
        )
        for value, label in zip(self.values.values(), labels):
            fig.add_trace(
                go.Scatter(
                    x=np.sort(value.values),
                    y=np.arange(value.n_sims) / value.n_sims,
                    name=label,
                )
            )
        fig.update_xaxes(title_text="Value")
        fig.update_yaxes(title_text="Cumulative Probability")
        fig.show()
