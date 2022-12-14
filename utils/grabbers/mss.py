import mss
import numpy


class Grabber:
    type = "mss"
    sct = mss.mss()

    def get_image(self, grab_area):
        """
        Make a screenshot of a given area and return it.
        :param grab_area: Format is {"top": 40, "left": 0, "width": 800, "height": 640}
        :return: numpy array
        """
        # noinspection PyTypeChecker
        return numpy.array(self.sct.grab(grab_area))
