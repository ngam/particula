""" the particule class
"""
# pylint: disable=too-many-instance-attributes
import numpy as np

from particula import u
from particula.constants import (AVOGADRO_NUMBER, BOLTZMANN_CONSTANT,
                                 ELECTRIC_PERMITTIVITY,
                                 ELEMENTARY_CHARGE_VALUE)
from particula.util.dimensionless_coagulation import DimensionlessCoagulation
from particula.util.distribution_discretization import discretize
from particula.util.friction_factor import frifac
from particula.util.fuchs_sutugin import fsc
from particula.util.input_handling import (in_density, in_handling, in_length,
                                           in_radius, in_scalar, in_volume,
                                           in_mass)
from particula.util.knudsen_number import knu
from particula.util.molecular_enhancement import mol_enh
from particula.util.particle_mass import mass
from particula.util.particle_surface import area
from particula.util.radius_cutoff import cut_rad
from particula.util.reduced_quantity import reduced_quantity as redq
from particula.util.rms_speed import cbar
from particula.util.slip_correction import scf
from particula.util.vapor_flux import phi
from particula.util.wall_loss import wlc
from particula.util.kelvin_correction import kelvin_term
from particula.vapor import Vapor


class ParticleDistribution(
    Vapor
):  # pylint: disable=too-many-instance-attributes
    """ starting a particle distribution from continuous pdf
    """

    def __init__(self, **kwargs):
        """  particle distribution objects.
        """
        super().__init__(**kwargs)

        self.spacing = kwargs.get("spacing", "linspace")
        self.nbins = in_scalar(kwargs.get("nbins", 1000)).m
        self.nparticles = in_scalar(kwargs.get("nparticles", 1e5)).m
        self.volume = in_volume(kwargs.get("volume", 1e-6))
        self.cutoff = in_scalar(kwargs.get("cutoff", 0.9999)).m
        self.gsigma = in_scalar(kwargs.get("gsigma", 1.25)).m
        self.mode = in_radius(kwargs.get("mode", 100e-9))
        # customize the radius
        self.force_radius_start = in_radius(
            kwargs.get("radius_start", 8392))
        self.force_radius_end = in_radius(
            kwargs.get("radius_end", 8392))
        self.force_radius_step = in_radius(
            kwargs.get("radius_step", 8392))

    def pre_radius(self):
        """ Returns the radius space of the particles

            Utilizing the utility cut_rad to get 99.99% of the distribution.
            From this interval, radius is made on a linspace with nbins points.
            Note: linspace is used here to practical purposes --- often, the
            logspace treatment will return errors in the discretization due
            to the asymmetry across the interval (finer resolution for smaller
            particles, but much coarser resolution for larger particles).
        """

        forcing_radius_start = None if self.force_radius_start.m == 8392 else (
            self.force_radius_start.m)
        forcing_radius_end = None if self.force_radius_end.m == 8392 else (
            self.force_radius_end.m)

        (rad_start, rad_end) = cut_rad(
            cutoff=self.cutoff,
            gsigma=self.gsigma,
            mode=self.mode,
            force_radius_start=forcing_radius_start,
            force_radius_end=forcing_radius_end,
        )
        if self.force_radius_step.m != 8392:
            nbins = int((rad_end-rad_start)/self.force_radius_step.m) + 2
            rad_end = rad_start + (nbins-1)*self.force_radius_step.m
        else:
            nbins = self.nbins

        if self.spacing == "logspace":
            radius = np.logspace(
                np.log10(rad_start),
                np.log10(rad_end),
                np.array(nbins).sum()
            )
        elif self.spacing == "linspace":
            radius = np.linspace(
                rad_start,
                rad_end,
                np.array(nbins).sum()
            )
        else:
            raise ValueError("Spacing must be 'logspace' or 'linspace'!")

        return radius*u.m

    def pre_discretize(self):
        """ Returns a distribution pdf of the particles

            Utilizing the utility discretize to get make a lognorm distribution
            via scipy.stats.lognorm.pdf:
                interval: the size interval of the distribution
                gsigma  : geometric standard deviation of distribution
                mode    : geometric mean radius of the particles
        """

        return discretize(
            interval=self.pre_radius(),
            disttype="lognormal",
            gsigma=self.gsigma,
            mode=self.mode,
            nparticles=self.nparticles
        )

    def pre_distribution(self):
        """ Returns a distribution pdf of the particles

            Utilizing the utility discretize to get make a lognorm distribution
            via scipy.stats.lognorm.pdf:
                interval: the size interval of the distribution
                gsigma  : geometric standard deviation of distribution
                mode    : geometric mean radius of the particles
        """

        return self.nparticles.sum()*self.pre_discretize()/self.volume


class ParticleInstances(ParticleDistribution):
    """ starting a particle distribution from single particles
    """

    def __init__(self, **kwargs):
        """  particle objects.
        """
        super().__init__(**kwargs)

        self.particle_radius = self.pre_radius() if kwargs.get(
            "particle_radius", None
        ) is None else in_radius(
            kwargs.get("particle_radius", None)
        )
        self.particle_number = self.nparticles if kwargs.get(
            "particle_radius", None
        ) is None else in_scalar(
            kwargs.get("particle_number", 1)
        )
        self.particle_density = in_density(
            kwargs.get("particle_density", 1000)
        )
        self.shape_factor = in_scalar(
            kwargs.get("shape_factor", 1)
        )
        self.volume_void = in_scalar(
            kwargs.get("volume_void", 0)
        )
        self.particle_charge = in_scalar(
            kwargs.get("particle_charge", 0)
        )
        self.particle_area_factor = in_scalar(
            kwargs.get("particle_area_factor", 1)
        )
        self.species_mass_fraction = in_mass(
            kwargs.get("species_mass_fraction", [1])
        )  # maybe here for speices masses, sulfate, water etc, not sure

    def particle_distribution(self):
        """ distribution
        """
        return (
            self.pre_distribution()
            if self.kwargs.get("particle_radius", None) is None
            else self.particle_number / self.particle_radius / self.volume
        )

    def particle_mass(self):
        """ Returns mass of particle.
        """
        return mass(
            radius=self.particle_radius,
            density=self.particle_density,
            shape_factor=self.shape_factor,
            volume_void=self.volume_void,
        )

    def particle_area(self):
        """ Returns particle's surface area
        """
        return area(
            radius=self.particle_radius,
            area_factor=self.particle_area_factor,
        )

    def knudsen_number(self):
        """ Returns particle's Knudsen number.
        """
        return knu(
            radius=self.particle_radius,
            mfp=self.mean_free_path(),
        )

    def slip_correction_factor(self):
        """ Returns particle's Cunningham slip correction factor.
        """
        return scf(
            radius=self.particle_radius,
            knu=self.knudsen_number(),
        )

    def friction_factor(self):
        """ Returns a particle's friction factor.
        """
        return frifac(
            radius=self.particle_radius,
            dynamic_viscosity=self.dynamic_viscosity(),
            scf=self.slip_correction_factor(),
        )


class ParticleCondensation(ParticleInstances):
    """ calculate some condensation stuff
    """

    def __init__(self, **kwargs):
        """ more particle objects.
        """
        super().__init__(**kwargs)
        self.particle_formation_rate = in_handling(
            kwargs.get("particle_formation_rate", 0),
            u.m**-4/u.s
        )
        self.kappa = in_scalar(
            kwargs.get("kappa", 1)
        )
        self.kwargs = kwargs

    def molecular_enhancement(self):
        """ molecular enhancement
        """
        return mol_enh(
            vapor_size=self.vapor_radius,
            particle_size=self.particle_radius
        )

    def condensation_redmass(self):
        """ red mass
        """
        return redq(
            self.vapor_molec_wt,
            np.transpose([self.particle_mass().m]) *
            self.particle_mass().u*AVOGADRO_NUMBER
        ).reshape(self.particle_radius.size, -1)

    def vapor_speed(self):
        """ vapor speed
        """
        return cbar(
            temperature=self.temperature,
            molecular_weight=self.condensation_redmass(),
            gas_constant=self.gas_constant,
        )/4

    def fuchs_sutugin(self):
        """ the fuchs-sutugin correction
        """
        return fsc(
            knu_val=self.knudsen_number(), alpha=self.vapor_attachment
        )

    def vapor_flux(self):
        """ vapor flux
        """
        return phi(
            particle_area=self.particle_area(),
            molecular_enhancement=self.molecular_enhancement(),
            vapor_attachment=self.vapor_attachment,
            vapor_speed=self.vapor_speed(),
            driving_force=self.driving_force(),
            fsc=self.fuchs_sutugin(),
        )

    def particle_growth(self):
        """ particle growth in m/s
        """
        result = self.vapor_flux() * 2 / (
            self.vapor_density *
            self.particle_radius.reshape(-1, 1)**2 *
            np.pi *
            self.shape_factor
        )
        return (
            result if result.shape == self.particle_radius.shape
            else result.sum(axis=1)
        )

    def particle_saturation_ratio(self):
        """
        Calculates the saturation ratio of the particle at its surface,
        accounting for the Kelvin effect.

        Returns:
        -------
        float
            The saturation ratio of the particle at its surface.
        """
        # future: add dry radius to particle object
        dry_radius = self.particle_radius

        return (
            (self.particle_radius**3 - dry_radius**3)
            / np.maximum(
                self.particle_radius**3 - dry_radius**3 * (1.0 - self.kappa),
                1.0e-30,
            )
            * kelvin_term(self.particle_radius, **self.kwargs)
        )


class ParticleWallLoss(ParticleCondensation):
    """ continuing...
    """

    def __init__(self, **kwargs):
        """ more particle objects.
        """
        super().__init__(**kwargs)
        self.wall_loss_approximation = str(
            kwargs.get("wall_loss_approximation", "none")
        )
        self.chamber_radius = in_length(
            kwargs.get("chamber_radius", 3)
        )
        self.kwargs = kwargs

    def wall_loss_coefficient(self):
        """ Returns a particle's wall loss coefficient.
        """
        return wlc(
            approx=self.wall_loss_approximation
        )


class Particle(ParticleWallLoss):
    """ the Particle class!
    """

    def __init__(self, **kwargs):
        """ particle objects.
        """
        super().__init__(**kwargs)

        self.elementary_charge_value = in_handling(
            kwargs.get("elementary_charge_value", ELEMENTARY_CHARGE_VALUE),
            u.C
        )
        self.electric_permittivity = in_handling(
            kwargs.get("electric_permittivity", ELECTRIC_PERMITTIVITY),
            u.F/u.m
        )
        self.boltzmann_constant = in_handling(
            kwargs.get("boltzmann_constant", BOLTZMANN_CONSTANT),
            u.m**2*u.kg/u.s**2/u.K
        )

        self.kwargs = kwargs

    def _coag_prep(self, other: "Particle"):
        """ get all related quantities to coulomb enhancement
        """
        return DimensionlessCoagulation(
            radius=self.particle_radius,
            other_radius=other.particle_radius,
            density=self.particle_density,
            other_density=other.particle_density,
            charge=self.particle_charge,
            other_charge=other.particle_charge,
            temperature=self.temperature,
            elementary_charge_value=self.elementary_charge_value,
            electric_permittivity=self.electric_permittivity,
            boltzmann_constant=self.boltzmann_constant,
            coag_approx=self.coagulation_approximation,
        )

    def reduced_mass(self, other: "Particle" = None):
        """ Returns the reduced mass.
        """
        return self._coag_prep(other or self).get_red_mass()

    def reduced_friction_factor(self, other: "Particle" = None):
        """ Returns the reduced friction factor between two particles.
        """
        return self._coag_prep(other or self).get_red_frifac()

    def coulomb_potential_ratio(self, other: "Particle" = None):
        """ Calculates the Coulomb potential ratio.
        """
        return self._coag_prep(other or self).get_ces()[0]

    def coulomb_enhancement_kinetic_limit(self, other: "Particle" = None):
        """ Kinetic limit of Coulomb enhancement for particle--particle
            cooagulation.
        """
        return self._coag_prep(other or self).get_ces()[1]

    def coulomb_enhancement_continuum_limit(self, other: "Particle" = None):
        """ Continuum limit of Coulomb enhancement for particle--particle
            coagulation.
        """
        return self._coag_prep(other or self).get_ces()[2]

    def diffusive_knudsen_number(self, other: "Particle" = None):
        """ Diffusive Knudsen number.
        """
        return self._coag_prep(other or self).get_diff_knu()

    def dimensionless_coagulation(self, other: "Particle" = None):
        """ Dimensionless particle--particle coagulation kernel.
        """
        return self._coag_prep(other or self).coag_less()

    def coagulation(self, other: "Particle" = None):
        """ Dimensioned particle--particle coagulation kernel
        """
        return self._coag_prep(other or self).coag_full()
