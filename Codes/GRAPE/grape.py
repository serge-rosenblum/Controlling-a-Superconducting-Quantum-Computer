# Imports
import time
import matplotlib.pyplot as plt
import numpy as np
import scipy.optimize as spopt
from matplotlib.pyplot import subplots
import qutip as qt
import warnings
import scipy.linalg
# warnings.filterwarnings('ignore')
a = 0.1*10


class GrapePulse:
    """
    A class used to represent a pulse to be optimized by GRAPE

    ...

    Attributes
    ----------
    :param ndarray psi_initial:
        The initial state of the qubit
    :param ndarray psi_target:
        The desired state of the qubit
    :param float total_time:
        The total time of the pulse
    :param float num_time_steps:
        Number of time divisions, the time vector is given by t = numpy.linspace(0, total_time, num_time_steps)
    :param ndarray base_hamiltonian:
        The hamiltonian of the system  that is not time dependent(not controled by the drives)
    :param list(ndarray) drive_hamiltonians:
        List of the time dependent hamiltonians(the list itself is not time dependent), The total, time dependent
        hamiltonian is given by
            H (t) = base_hamiltonian + drive_hamiltonian[0] * pulse0(t) + drive_hamiltonian[1] * pulse1(t) + . . .
    :param numpy.ndarray initial_pulse:
        The initial GRAPE pulse guess, the pulse matrix is of the shame [n,m] where n is the number of drive
        hamiltonians( len(drive_hamiltonians) i.e. different pulse for each hamiltonian) and m is the number of time
        steps(an attribute)
    :param boolean constraints:
        Determine weather or not to constraint the GRAPE with amplitude/slope/etc penelties
    :param float max_amp:
        The absolute maximum amplitude of the pulse, this is the hard cut-off
    :param float epsilon_soft_max:
        The soft limit on the amplitude - NOT CURRENTLY USED
    :param float lambda_band_lin:
        The strength of the slope(derivative) penalty, the bigger this is the smoother the final pulse would be
    :param boolean fix_amp_max:
        If false, the initial guess would be changed a bit by the process of the hard cut-off. Making this true will fix
        the problem but if the initial guess amplitude exceeds the maximum amplitude an error will be raised
    :param boolean print_fidelity:
        Weather or not to print the fidelity of each iteration
    """

    def __init__(self, psi_initial, psi_target,  total_time, num_time_steps, base_hamiltonian, drive_hamiltonians,
                 initial_pulse, constraints=True, max_amp=1, epsilon_soft_max=1, lambda_band_lin=0.1,
                 lambda_amp_lin=0.03, fix_amp_max=True, print_fidelity=False):
        try:
            # TODO: Change to auto initialize
            self.psi_initial = np.array(psi_initial)
            self.psi_target = np.array(psi_target)
            self.total_time = np.float(total_time)
            self.num_time_steps = int(num_time_steps)
            self.base_hamiltonian = np.array(base_hamiltonian)
            self.num_drives = len(drive_hamiltonians)
            self.drive_hamiltonians = []
            for i in range(self.num_drives):
                self.drive_hamiltonians.append(np.array(drive_hamiltonians[i]))
            self.initial_pulse = np.array(initial_pulse)
            self.constraints = bool(constraints)
            self.max_amp = np.float(max_amp)
            self.epsilon_soft_max = np.float(epsilon_soft_max)
            self.lambda_band_lin = np.float(lambda_band_lin)
            self.lambda_amp_lin = np.float(lambda_amp_lin)
            self.fix_amp_max = bool(fix_amp_max)
            self.print_fidelity = bool(print_fidelity)
        except ValueError:
            raise ValueError("Invalid Input")
        except TypeError:
            raise TypeError('Invalid Input')

        self.times = np.linspace(0.0, total_time, num_time_steps)
        self.dt = total_time / num_time_steps

        self._check_input()

    def _check_input(self):
        """
        Check that all the input of the GRAPE pulse are actually valid and in the right type/dimension
        :return: None
        """
        if len(self.psi_initial.shape) == 1:
            warnings.warn("Initial state of shape" + str(self.psi_initial.shape) + " is a row vector(shape == (N,))."
                          " The initial state should be a column vector(quantum state is a \"ket |>\"). \n"
                          "This will be fixed automatically but it's a bad practice to live it like so")
            self.psi_initial = np.reshape(
                self.psi_initial, (self.psi_initial.shape[0], 1))

        if len(self.psi_target.shape) == 1:
            warnings.warn("Target state of shape" + str(self.psi_target.shape) + " is a row vector(shape == (N,))."
                          " The initial state should be a column vector(quantum state is a \"ket |>\"). \n"
                          "This will be fixed automatically but it's a bad practice to live it like so")
            self.psi_target = np.reshape(
                self.psi_target, (self.psi_target.shape[0], 1))

        # Check that initial and target qubit states are actually qubit states in terms of dimensions
        init_shape = self.psi_initial.shape
        targ_shape = self.psi_target.shape
        # if not (init_shape == (2,) and targ_shape == (2,)):
        # raise ValueError('Non-pure quantum states are not currently supported in this GRAPE implementation, Make'
        # 'sure psi_initial and psi_target are of shape (2,). \npsi_initial=' + str(init_shape)
        # + '\npsi_target=' + str(targ_shape))

        # Checks if initial pulse is of correct dimensions based on the amount of drives
        if not(self.initial_pulse.flatten().shape == (self.num_drives * self.num_time_steps),):
            raise ValueError('The initial pulse must be of shape \n*amount of drive hamiltonians* by '
                             '*number of time steps*, or \n*amount of drive hamiltonians* times '
                             '*number of time steps* by 1 \n'
                             'initial_pulse is ' +
                             str(self.initial_pulse.shape) +
                             ' but it needs to be '
                             + str((self.num_drives, self.num_time_steps)))

        # Checks for valid input pulse(pulse is valid if it does not exceed the max amp) if fix_amp_max is True
        if self.fix_amp_max:
            if np.abs(np.max(self.initial_pulse)) > self.max_amp:
                raise ValueError('If \'fix_amp_max\' option is True, the initial guess MUST no exceed the maximum '
                                 'amplitude(max_amp)')

        return None

    def optimize(self):
        """
        Optimize the pulse with the GRAPE algorithm
        :return: A tuple, the first is the final pulse(same dimensions as the initial pulse) and the second
        is the final fidelity achieved by GRAPE, success is roughly if fidelity > 0.999
        """
        # Using the L-BFGS-B optimization algorithm to find the minimum of the cost function
        if self.fix_amp_max:
            result = spopt.fmin_l_bfgs_b(self.cost,
                                         np.arctanh(
                                             self.initial_pulse / self.max_amp), self.cost_gradient,
                                         factr=1e12)
        else:
            result = spopt.fmin_l_bfgs_b(self.cost, np.arctanh(self.initial_pulse / self.max_amp),
                                         self.cost_gradient, factr=1e12)
        result = (result[0].reshape(self.num_drives,
                                    self.num_time_steps), result[1])
        self.run_operator(result[0], show_prob=True)
        return result[0:2]

    def cost(self, in_pulse):
        """
        The cost function that the optimization algorithm seek to minimize
        :param in_pulse:
        :return: The cost function -(fidelity - penalties)
        """
        in_pulse = in_pulse.reshape(self.num_drives, self.num_time_steps)

        if self.constraints:
            # pulse = self.max_amp * np.tanh(in_pulse)
            pulse = in_pulse
        else:
            pulse = in_pulse
        # for i in range(self.num_drives):
        #     pulse[i, 0] = 0
        #     pulse[i, -1] = 0
        # Calculates the final state and the fidelity from the run_operator function
        itime = time.time()
        # print("Before", np.max(pulse))
        psi_final, fid = self.run_operator(pulse)
        # print("Cost time: ", str(time.time() - itime), "seconds")
        final_fid = -fid + self.constraints * self.constraint(pulse)
        # print("After", np.max(pulse))
        # plt.plot(self.times, pulse[0])
        return final_fid

    def cost_gradient(self, in_pulse, debug_fidelity=False):
        """
        The gradient of the cost function used to minimize the cost function with the optimization algorithm
        :param in_pulse:
        :param bool debug_fidelity: Displays graphs comparing analytical and numerical fidelities for debugging
        :return: The total gradient of the cost function
        """

        in_pulse = in_pulse.reshape(self.num_drives, self.num_time_steps)
        if self.constraints:
            pulse = self.max_amp * np.tanh(in_pulse)
            pulse = in_pulse
        else:
            pulse = in_pulse
        # for i in range(self.num_drives):
            # pulse[i, 0] = 0
            # pulse[i, -1] = 0
        # Initialize the elements used to calculate the gradient efficiently
        psi_fwd = []

        U_k = self.eigy_expm((1j * self.dt) * self.H(pulse))
        # U_k = self.U_k

        for k in range(self.num_time_steps+1):
            if k == 0:
                psi_fwd.append(self.psi_initial)
            else:
                psi_fwd.append(U_k[k - 1] @ psi_fwd[-1])

        psi_bwd = np.array([np.identity(len(self.psi_initial))]
                           * (self.num_time_steps+1), dtype=complex)
        # for k in range(1, self.num_time_steps):
        #     psi_bwd[self.num_time_steps - k -
        #             1] = psi_bwd[self.num_time_steps - k] @ U_k[self.num_time_steps - k]

        for k in reversed(range(self.num_time_steps-1)):
            psi_bwd[k] = psi_bwd[k+1] @ U_k[k+1]

        self.psi_bwd = psi_bwd  # psi_bwd before it is multiplyied by the target state

        for k in range(self.num_time_steps + 1):
            # TODO: Might need changeing
            psi_bwd[k] = self.psi_target.conj().T @ psi_bwd[k]

        prod = np.identity(len(self.psi_initial))
        for k in range(self.num_time_steps):
            prod = U_k[k] @ prod
        c = self.psi_target.conj().T @ prod @ self.psi_initial  # TODO: Might need changeing

        itime = time.time()
        c_final = np.ndarray(self.num_time_steps *
                             self.num_drives, dtype=complex)
        for i, H_k in enumerate(self.drive_hamiltonians):  # TODO: Might need changing
            for k in range(self.num_time_steps):
                c_final[k + i*self.num_time_steps] = psi_bwd[k-1,
                                                             0] @ H_k @ psi_fwd[k]
            # c_final[i*self.num_time_steps : (i+1)*self.num_time_steps] = psi_bwd[:, 0] @ H_k @ psi_fwd[:]
        c_final = 2 * np.real(c * np.conjugate(1j * self.dt * c_final))
        # print("Gradient time: ", str(time.time() - itime), "Seconds")

        # *np.ndarray.flatten(self.max_amp/(np.cosh(in_pulse) ** 2))
        self.psi_fwd = psi_fwd

        gradient = -c_final + self.constraints * \
            self.constraint_gradient(pulse).flatten()
        # print("AVG GRAD: ", np.average(np.abs(c_final)))

        # gradient = -c_final

        if debug_fidelity:
            c_fin_transpose = np.transpose(gradient)
            fig, axes = subplots(2, 2)
            axes[0, 0].set_title("gradient")
            axes[0, 0].plot(
                self.times, -c_fin_transpose[0:self.num_time_steps])
            axes[0, 0].plot(
                self.times, -c_fin_transpose[self.num_time_steps:2 * self.num_time_steps])
            axes[0, 0].plot(self.times, np.zeros(self.num_time_steps))

            axes[1, 0].set_title("rough estimation of gradient")
            grad = -spopt.approx_fprime(np.ndarray.flatten(
                in_pulse), self.cost, 1e-5)
            # grad2 = -spopt.approx_fprime(np.ndarray.flatten(
            # in_pulse), self.cost, 1e-1)
            axes[1, 0].plot(self.times, grad[0:self.num_time_steps])
            axes[1, 0].plot(self.times, grad[self.num_time_steps:])
            # axes[1, 0].plot(self.times, grad2[0:self.num_time_steps])
            # axes[1, 0].plot(self.times, grad2[self.num_time_steps:])
            axes[1, 0].plot(self.times, np.zeros(self.num_time_steps))

            axes[0, 1].set_title("QI")
            axes[0, 1].plot(self.times, pulse[0])
            axes[0, 1].plot(self.times, np.zeros(self.num_time_steps))

            axes[1, 1].set_title("QQ")
            axes[1, 1].plot(self.times, in_pulse[0])
            axes[1, 1].plot(self.times, np.zeros(self.num_time_steps))

        # for i in range(self.num_drives):
        #     gradient[0, i*self.num_time_steps] = 0
        #     gradient[0, i*self.num_time_steps - 1] = 0

        return gradient

    def constraint(self, pulse):
        """
        Calculate the Lagrange multipliers to create penelties on the cost function to make 'soft' limits
        :param pulse:
        :return: The total Lagrange multipliers
        """
        pulse = pulse.reshape(self.num_drives, self.num_time_steps)
        slope = pulse[:, 1:] - pulse[:, :-1]
        bandwidth_constraint = np.sum(slope**2)
        amplitude_constraint = np.average(pulse**2)
        # print(np.max(pulse))
        # print(amplitude_constraint)
        # DRAG constraints
        # Initialize the elements used to calculate the gradient efficiently
        psi_fwd = []

        U_k = self.eigy_expm((1j * self.dt) * self.H(pulse))
        # U_k = self.U_k

        for k in range(self.num_time_steps+1):
            if k == 0:
                psi_fwd.append(self.psi_initial)
            else:
                psi_fwd.append(U_k[k - 1] @ psi_fwd[-1])
        self.psi_fwd = psi_fwd
        # print(len(psi_fwd))

        # DRAG - start

        g_drag = 0
        # population = np.zeros(self.num_time_steps)
        state_2 = np.array([0, 0, 1])
        # print(psi_fwd[0].shape)
        for i in range(self.num_time_steps+1):
            g_drag += np.abs(state_2 @ psi_fwd[i])**2
            # population[i] = np.abs(state_2 @ psi_fwd[i])**2
        # plt.plot(self.times, population)
        self.drag_sum = g_drag
        # print(g_drag)
        # DRAG - end
        constraint_total = self.lambda_amp_lin * amplitude_constraint \
            + self.lambda_band_lin * bandwidth_constraint \
            + g_drag*a

        # print("\n-)Constraint Total: ", constraint_total) if self.print_fidelity else None
        # print("AVG CONST", constraint_total)
        # print(constraint_total)
        # print("DRAG ", g_drag[0, 0]*a)
        return constraint_total.flatten()

    def constraint_gradient(self, pulse):
        """
        Calculate the gradient of the Lagrange multipliers for the optimization algorithm
        :param pulse:
        :return: The gradient of the Lagrange multipliers
        """
        # print(pulse.shape)
        constraint_total = np.zeros(pulse.shape)
        g_band_lin = np.zeros(pulse.shape)
        g_amp_lin = np.zeros(pulse.shape)
        g_drag = np.zeros(pulse.shape)

        g_band_lin[:, 0] = -2 * (pulse[:, 1] - pulse[:, 0])
        g_band_lin[:, -1] = 2*(pulse[:, -1] - pulse[:, -2])
        g_band_lin[:, 1:-1] = 4 * pulse[:, 1:-1] - \
            2 * (pulse[:, 2:] + pulse[:, :-2])

        g_amp_lin = 2*pulse

        # DRAG - start
        # Initialize the elements used to calculate the gradient efficiently
        psi_fwd = self.psi_fwd
        # U_k = self.U_k

        U_k = self.eigy_expm((1j * self.dt) * self.H(pulse))

        state_2 = np.array([0, 0, 1])

        # psi_bwd = np.array([[np.identity(len(self.psi_initial))]*self.num_time_steps]*self.num_time_steps, dtype=complex)
        psi_bwd = np.array(
            [[np.identity(len(self.psi_initial))]], dtype=complex)
        psi_bwd = np.ones(
            [self.num_time_steps, self.num_time_steps, 1, 1])*psi_bwd
        # print(psi_bwd.shape)
        # print(psi_bwd[0, 0])
        for i in range(self.num_time_steps):
            for k in range(0, i-1):
                if k != 0:
                    psi_bwd[i, i-k] = U_k[k]@psi_bwd[i, i - k + 1]
                else:
                    # psi_bwd[i, i] = U_k[i] @ np.identity(len(self.psi_initial))
                    pass
        phi_bwd = np.zeros(
            [self.num_time_steps, self.num_time_steps, 3], dtype=complex)

        for i in range(self.num_time_steps):
            for k in range(self.num_time_steps):
                # print((state_2@psi_bwd[i, k]).shape)
                phi_bwd[i, k] = state_2@psi_bwd[i, k]

        # psi_bwd = self.psi_bwd

        # print(phi_bwd[0, 0].shape)
        # itime = time.time()

        # population = np.zeros(self.num_time_steps, dtype=complex)
        # for i in range(self.num_time_steps-1):
        #     # g_drag[j, k] = 0
        #     for k in range(0, i):
        #         for j in range(self.num_drives):
        #             # print(U_k[-1]@U_k[-2])
        #             # print("psi:", psi_bwd[k].shape)
        #             phi_bwd = state_2 @  (psi_bwd_inv[i+1] @ psi_bwd[k+1])
        #             overlap = 1j*self.dt * \
        #                 (phi_bwd @ self.drive_hamiltonians[j] @ psi_fwd[i])
        #             # population[i] += overlap[0]
        #             # print("phi:", phi_bwd.shape)
        #             # print(overlap.shape)
        #             # c_final = 2 * np.real(c * np.conjugate(1j * self.dt * c_final))
        #             # print("bwd", psi_bwd[i, k].shape)
        #             # print("fwd", psi_fwd[i].shape)
        #             # print("drive", self.drive_hamiltonians[j].shape)
        #             # print(overlap[0])

        #             g_drag[j, i] += 2 * \
        #                 np.real(self.drag_sum * np.conjugate(overlap[0]))
        # TODO: This can be much more efficient VVV
        psi_bwd = np.array(
            [np.identity(len(self.psi_initial))]*(self.num_time_steps+1), dtype=complex)
        # print(psi_bwd.shape)
        psi_bwd[-2] = U_k[-1]

        for k in reversed(range(self.num_time_steps-2)):
            psi_bwd[k] = psi_bwd[k+1]@U_k[k+1]

        psi_bwd_inv = np.linalg.inv(psi_bwd)
        # print(len(psi_fwd))

        a0 = -1
        a1 = -1
        a2 = 0
        a3 = 0
        a4 = 1

        for k in range(self.num_time_steps):
            for i in range(k, self.num_time_steps):
                # if k == 0:
                #     print("NOOO")
                for j in range(self.num_drives):
                    phi = state_2 @ psi_bwd_inv[i + a0] @ psi_bwd[k+a1]
                    overlap = a4*1j * self.dt * \
                        phi @ self.drive_hamiltonians[j] @ psi_fwd[k + a2]
                    cc = state_2 @ psi_fwd[i + a3]

                    # print(np.real(cc[0]))
                    g_drag[j, k] += a*2 * \
                        np.real(cc * np.conjugate(overlap[0]))

        # print(population.shape)
        # plt.figure()
        # plt.plot(self.times, population)
        # print("time bwd:", time.time() - itime)

        # DRAG - end

        constraint_total = self.lambda_band_lin * g_band_lin + \
            self.lambda_amp_lin*g_amp_lin + g_drag*a
        # print("AVG CONST GRAD", np.average(np.abs(constraint_total)))
        return constraint_total.flatten()

    def run_operator(self, pulse, show_bloch=False, calc_fidelity=True, show_prob=False):
        """
        Runs the pulse to get the final state and fidelity after driving the qubit
        :param pulse: Drive pulse to solve for the schrodinger equation
        :param boolean show_bloch: Weather or not to show the path of the qubit along the bloch sphere
        :param boolean calc_fidelity: Weather or not to calculate and return the fidelity
        :param boolean show_prob: Weather or not to show the probabilities of each state over the pulse
        :return:
        """
        prod = np.identity(len(self.psi_initial))
        if show_bloch:  # TODO: Defiantly need changing
            b = qt.Bloch()
            b.add_states(self.psi_initial)
            U_k = self.eigy_expm((1j * self.dt) * self.H(pulse))
            for k in range(self.num_time_steps):
                prod = U_k[k] @ prod
                b.add_states(prod * self.psi_initial, kind='point')
            psi_final = prod @ self.psi_initial
            b.add_states(psi_final)
            b.show()
        else:
            U_k = self.eigy_expm((1j * self.dt) * self.H(pulse))
            self.U_k = U_k

            if show_prob:
                U_ki = self.eigy_expm((1j * self.dt) *
                                      self.H(np.reshape(self.initial_pulse, (self.num_drives, self.num_time_steps))))
                initial_prob = np.zeros(
                    [len(self.psi_initial), self.num_time_steps])
                final_prob = np.zeros(
                    [len(self.psi_target), self.num_time_steps])
                fig, (ax1, ax2) = plt.subplots(1, 2, sharey=True)
                ax1.set_title("Initial")
                ax2.set_title("Final")
                leg = []
                wig = []
                for i in range(len(self.psi_initial)):
                    prod = np.identity(len(self.psi_initial))
                    prodi = np.identity(len(self.psi_initial))
                    leg.append("|" + str(i) + ">")
                    for k in range(self.num_time_steps):
                        prodi = U_ki[k] @ prodi
                        prod = U_k[k] @ prod
                        initial_prob[i, k] = np.abs(
                            (prodi @ self.psi_initial)[i]) ** 2
                        final_prob[i, k] = np.abs(
                            (prod @ self.psi_initial)[i]) ** 2
                        # wig.append(qt.Qobj(prod @ self.psi_initial, [[2, 5], [1, 1]]).ptrace(1))
                    ax1.plot(self.times, initial_prob[i, :])
                    ax2.plot(self.times, final_prob[i, :])
                ax1.legend(leg)
                psi_final = prod @ self.psi_initial
                # for i in range(10):
                #     print(int((len(wig)/10)*i))
                # qt.plot_wigner(qt.Qobj(prod @ self.psi_initial, [[2, 20], [1, 1]]).ptrace(1))
                return psi_final
            else:
                itime = time.time()
                for k in range(self.num_time_steps):
                    prod = U_k[k] @ prod
                # print("Operator time: ", str(time.time() - itime), "Seconds")
                psi_final = prod @ self.psi_initial  # TODO: Might need changing
                # print("OP Time: ", str(time.time() - itime))

        if calc_fidelity:
            fid = np.abs(self.psi_target.conj().T @ psi_final)[
                0, 0] ** 2  # np.abs is element-wise absolute value
            print("\n-> Fidelity: ", fid) if self.print_fidelity else None
            return psi_final, fid
        return psi_final

    def H(self, pulse):
        """
        Get the total hamiltonian(base + drive hamiltonians) of a given pulse at a given index
        :param pulse: Pulse to calculate the drive hamiltonian
        :param k: Index of the hamiltonian (from 0 to num_time_steps)
        :return: The total hamiltonian at index k
        """
        H = np.array([self.base_hamiltonian] *
                     self.num_time_steps)  # TODO: Might need changing
        # TODO: Might need changing
        HT = np.array([self.base_hamiltonian] * self.num_time_steps)
        # print(H[:,0,0].shape)
        for i, H_k in enumerate(self.drive_hamiltonians):
            H += pulse[i, :].reshape(self.num_time_steps, 1, 1)*H_k
            # itime = time.time()
            # for j in range(len(self.psi_initial)):
            #     for k in range(len(self.psi_initial)):
            #         H[:, j, k] += H_k[j, k]*pulse[i, :]
            # og = time.time() - itime
            # print("H og time: ", str(time.time() - itime))
            # a = pulse.reshape(self.num_time_steps*self.num_drives, 1, 1)*H_k
            # print(HT[i*self.num_time_steps:(i+1)*self.num_time_steps, :, :].shape)
            # print(i)
            # print(len(HT[:)
            # itime = time.time()
            # nonog = time.time() - itime
            # print("Improvement: ", str((nonog/og- 1)*100), "%")
            # print(HT-H)
            # H[:, 0, 1] += H_k[0, 1]*pulse[i, :]
            # H[:, 1, 0] += H_k[1, 0]*pulse[i, :]
            # H[:, 1, 1] += H_k[1, 1]*pulse[i, :]
        return H

    def eigy_expm(self, A):
        vals, vects = np.linalg.eig(A)
        return np.einsum('...ik, ...k, ...kj -> ...ij',
                         vects, np.exp(vals), np.linalg.inv(vects))
        # for i in range(len(A)):
        #     A[i] = scipy.linalg.expm(A[i])
        # return A
